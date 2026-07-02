package verilog

import (
	"regexp"
	"sort"
	"strings"
)

// autosenseKeywords ports _AUTOSENSE_KEYWORDS.
var autosenseKeywords = map[string]bool{
	"always": true, "begin": true, "end": true, "if": true, "else": true,
	"case": true, "endcase": true, "assign": true, "default": true,
	"posedge": true, "negedge": true, "or": true, "and": true, "logic": true,
	"reg": true, "wire": true, "initial": true, "input": true, "output": true,
	"inout": true, "module": true, "endmodule": true, "task": true,
	"endtask": true, "function": true, "endfunction": true, "fork": true,
	"join": true, "generate": true, "endgenerate": true, "repeat": true,
	"while": true, "for": true, "forever": true, "integer": true, "bit": true,
}

var autosenseRe = regexp.MustCompile(`(?is)(always\s*@\s*)\(([^)]*/\*AUTOSENSE\*/[^)]*)\)`)
var identifierScanRe = regexp.MustCompile(`\b([a-zA-Z_]\w*)\b`)
var autosenseTailRe = regexp.MustCompile(`(?is)/\*AUTOSENSE\*/.*`)
var alwaysKwRe = regexp.MustCompile(`\b(begin|end|case|endcase|fork|join)\b`)

// extractAlwaysBlockBody ports _extract_always_block_body.
func extractAlwaysBlockBody(content string, startPos int) string {
	body := pyStrip(content[startPos:])
	if strings.HasPrefix(body, "begin") {
		stack := 0
		for _, m := range alwaysKwRe.FindAllStringSubmatchIndex(body, -1) {
			switch body[m[2]:m[3]] {
			case "begin", "case", "fork":
				stack++
			case "end", "endcase", "join":
				stack--
			}
			if stack == 0 {
				return body[:m[1]]
			}
		}
	} else if idx := strings.Index(body, ";"); idx != -1 {
		return body[:idx+1]
	}
	return body
}

// signalIsRead ports _signal_is_read.
func signalIsRead(name, cleanBody string) bool {
	re := regexp.MustCompile(`\b` + regexp.QuoteMeta(name) + `\b`)
	for _, m := range re.FindAllStringIndex(cleanBody, -1) {
		suffix := pyLStrip(cleanBody[m[1]:])
		if strings.HasPrefix(suffix, "[") {
			stack := 0
			skip := 0
			for i := 0; i < len(suffix); i++ {
				switch suffix[i] {
				case '[':
					stack++
				case ']':
					stack--
				}
				skip = i + 1
				if stack == 0 {
					break
				}
			}
			suffix = pyLStrip(suffix[skip:])
		}
		isBlocking := strings.HasPrefix(suffix, "=") && !strings.HasPrefix(suffix, "==")
		isNonBlocking := strings.HasPrefix(suffix, "<=") && !strings.HasPrefix(suffix, "<==")
		if !(isBlocking || isNonBlocking) {
			return true
		}
	}
	return false
}

// ExpandAutosense ports expand_autosense: fill always @(/*AUTOSENSE*/...) with
// the signals read in the block body.
func ExpandAutosense(content, filePath string, proj *Project) string {
	localSignals := getLocalSignals(content)
	locs := autosenseRe.FindAllStringSubmatchIndex(content, -1)
	if locs == nil {
		return content
	}
	var b strings.Builder
	last := 0
	for _, loc := range locs {
		b.WriteString(content[last:loc[0]])
		prefix := content[loc[2]:loc[3]]
		parenContent := content[loc[4]:loc[5]]

		cleanBody := StripComments(extractAlwaysBlockBody(content, loc[1]))
		detected := map[string]bool{}
		for _, m := range identifierScanRe.FindAllStringSubmatch(cleanBody, -1) {
			name := m[1]
			if localSignals[name] && !autosenseKeywords[name] && signalIsRead(name, cleanBody) {
				detected[name] = true
			}
		}
		if len(detected) == 0 {
			b.WriteString(content[loc[0]:loc[1]])
			last = loc[1]
			continue
		}
		sorted := make([]string, 0, len(detected))
		for s := range detected {
			sorted = append(sorted, s)
		}
		sort.Strings(sorted)
		newParen := autosenseTailRe.ReplaceAllString(parenContent, "/*AUTOSENSE*/"+strings.Join(sorted, " or "))
		b.WriteString(prefix + "(" + newParen + ")")
		last = loc[1]
	}
	b.WriteString(content[last:])
	return b.String()
}
