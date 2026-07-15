package verilog

import (
	"regexp"
	"strings"
)

// typeDeclRe ports _TYPE_DECL_RE. `\b…\b\s*` (and `\s*` after the width)
// tolerate the no-space forms `wire[7:0] a;` / `reg[3:0] b;`; the `\b` after the
// keyword still rejects identifiers such as `wireless` / `regfile`.
var typeDeclRe = regexp.MustCompile(`\b(wire|reg|logic|integer|bit|real|byte|shortint|int|longint)\b\s*(\[.*?\]\s*)?([\w\s,]+);`)

// scanTypeDecls ports _scan_type_decls: {signal name: width} for wire/reg/logic
// declarations.
func scanTypeDecls(content string) map[string]string {
	result := map[string]string{}
	for _, m := range typeDeclRe.FindAllStringSubmatch(content, -1) {
		width := pyStrip(m[2])
		for _, name := range strings.Split(m[3], ",") {
			clean := pyStrip(strings.SplitN(pyStrip(name), "=", 2)[0])
			if clean != "" {
				if _, ok := result[clean]; !ok {
					result[clean] = width
				}
			}
		}
	}
	return result
}

// getLocalSignalWidths ports get_local_signal_widths.
func getLocalSignalWidths(content string) map[string]string {
	widths := map[string]string{}
	for _, mod := range ParseModules(content) {
		for _, p := range mod.Ports {
			if _, ok := widths[p.Name]; !ok {
				widths[p.Name] = p.Width
			}
		}
	}
	for name, w := range scanTypeDecls(StripComments(content)) {
		if _, ok := widths[name]; !ok {
			widths[name] = w
		}
	}
	return widths
}

var whitespaceRe = regexp.MustCompile(`\s+`)

// widthsMismatch ports _widths_mismatch.
func widthsMismatch(w1, w2 string) bool {
	if w1 == "" || w2 == "" {
		return false
	}
	return whitespaceRe.ReplaceAllString(w1, "") != whitespaceRe.ReplaceAllString(w2, "")
}

var paramNameRe = regexp.MustCompile(`(?m)\b(parameter|localparam)\b\s+(?:.*?\b)?(\w+)\s*=`)
var identifierRe = regexp.MustCompile(`^[A-Za-z_]\w*$`)

// getLocalSignals ports get_local_signals: names of ports, params, and
// wire/reg/logic declarations already present locally.
func getLocalSignals(content string) map[string]bool {
	signals := map[string]bool{}
	c := StripComments(content)
	for _, mod := range ParseModules(content) {
		for _, p := range mod.Ports {
			signals[p.Name] = true
		}
	}
	for name := range scanTypeDecls(c) {
		signals[name] = true
	}
	for _, m := range paramNameRe.FindAllStringSubmatch(c, -1) {
		signals[m[2]] = true
	}
	return signals
}

// collectAutoDecls ports _collect_auto_decls: build declarations for
// sub-instance ports matching filterDirection, skipping locally-declared
// signals and non-identifier connections (constants/expressions). The Python
// manual-width warning is stdout-only and does not affect the returned decls,
// so it is omitted here.
func collectAutoDecls(contentForSignals string, insts []Inst, filterDirection, emitKeyword string, semicolon bool, proj *Project) []string {
	localSignals := getLocalSignals(contentForSignals)
	suffix := ""
	if semicolon {
		suffix = ";"
	}
	var decls []string
	seen := map[string]bool{}
	for _, inst := range insts {
		moduleDef := proj.Modules[inst.ModuleName]
		if moduleDef == nil {
			continue
		}
		for _, conn := range inst.Ports {
			var pDef *Port
			for i := range moduleDef.Ports {
				if moduleDef.Ports[i].Name == conn.Name {
					pDef = &moduleDef.Ports[i]
					break
				}
			}
			if pDef == nil || pDef.Direction != filterDirection {
				continue
			}
			base := pyStrip(strings.SplitN(conn.Signal, "[", 2)[0])
			if !identifierRe.MatchString(base) {
				continue // constant / literal / expression — not a net
			}
			if !localSignals[base] {
				width := ""
				if pDef.Width != "" {
					width = pDef.Width + " "
				}
				decl := emitKeyword + " " + width + base + suffix
				if !seen[decl] {
					decls = append(decls, decl)
					seen[decl] = true
					localSignals[base] = true
				}
			}
		}
	}
	return decls
}

// blockAfterTagRe matches a `// Beginning … // End of automatics` block left by
// a previous ANSI expansion immediately after the tag (anchored at start).
var blockAfterTagRe = regexp.MustCompile(`(?s)^\s*// Beginning of automatic \w+.*?// End of automatics`)

// expandAutoPort ports _expand_auto_port (AUTOINPUT / AUTOOUTPUT), handling both
// ANSI (port list) and Non-ANSI (body) contexts.
func expandAutoPort(content, filePath, tagName, direction string, proj *Project) string {
	ansiRe := regexp.MustCompile(`(?is)(\bmodule\s+(\w+)\s*)(#\s*\(.*?\))?\s*\(([^;]*?(/\*` + tagName + `\*/)[^;]*?)\)\s*;`)
	if loc := ansiRe.FindStringSubmatchIndex(content); loc != nil {
		modStart := content[loc[2]:loc[3]]
		params := ""
		if loc[6] >= 0 {
			params = content[loc[6]:loc[7]]
		}
		portBlock := content[loc[8]:loc[9]]
		tag := content[loc[10]:loc[11]]

		tagIndex := strings.Index(portBlock, tag)
		before := pyStrip(portBlock[:tagIndex])
		afterRaw := portBlock[tagIndex+len(tag):]
		// Idempotency: strip a `// Beginning … // End of automatics` block a
		// previous run left right after the tag, so a re-run replaces it.
		existingBlock := blockAfterTagRe.FindString(afterRaw)
		// Manual ports after the tag; drop the leading separating comma so we can
		// re-emit them on their own line below the block.
		after := pyStrip(strings.TrimLeft(pyStrip(afterRaw[len(existingBlock):]), ","))

		contentForSignals := strings.Replace(content, tag, "", 1)
		if existingBlock != "" {
			contentForSignals = strings.Replace(contentForSignals, existingBlock, "", 1)
		}
		insts := GetInstantiations(content)
		newDecls := collectAutoDecls(contentForSignals, insts, direction, direction, false, proj)

		head := portBlock[:tagIndex]
		var newPortBlock string
		if len(newDecls) == 0 {
			// Nothing to add: bare tag, keep any trailing manual ports.
			newPortBlock = head + tag
			if after != "" {
				newPortBlock += ", " + after
			}
		} else {
			// Keep the tag and wrap the generated decls in the same Emacs
			// `// Beginning … // End of automatics` markers the body form uses,
			// so DeleteAll (autoSignalBlockRe) can reverse it. Trailing manual
			// ports go on their own line so the End comment does not swallow them.
			commentType := "inputs"
			if direction != "input" {
				commentType = "outputs"
			}
			decls := strings.Join(newDecls, ",\n    ")
			decls = applyCommaContext(decls, before, "")
			if after != "" && !strings.HasSuffix(pyRStrip(decls), ",") {
				decls = pyRStrip(decls) + ","
			}
			newPortBlock = head + tag +
				"\n    // Beginning of automatic " + commentType + "\n    " +
				decls + "\n    // End of automatics"
			if after != "" {
				newPortBlock += "\n    " + after
			}
		}
		header := pyRStrip(modStart)
		if params != "" {
			header += " " + pyStrip(params)
		}
		replacement := header + " (" + pyRStrip(newPortBlock) + "\n);"
		return content[:loc[0]] + replacement + content[loc[1]:]
	}

	bodyRe := regexp.MustCompile(`(?is)(/\*` + tagName + `\*/)(\s*// Beginning.*?// End of automatics)?`)
	loc := bodyRe.FindStringSubmatchIndex(content)
	if loc == nil {
		return content
	}
	tag := content[loc[2]:loc[3]]
	existingBlock := ""
	if loc[4] >= 0 {
		existingBlock = content[loc[4]:loc[5]]
	}
	contentForSignals := content
	if existingBlock != "" {
		contentForSignals = strings.Replace(content, existingBlock, "", 1)
	}
	insts := GetInstantiations(content)
	newDecls := collectAutoDecls(contentForSignals, insts, direction, direction, true, proj)
	if len(newDecls) == 0 {
		return content[:loc[0]] + tag + content[loc[1]:]
	}
	commentType := "inputs"
	if direction != "input" {
		commentType = "outputs"
	}
	blockContent := strings.Join(newDecls, "\n    ")
	replacement := "/*" + tagName + "*/\n    // Beginning of automatic " + commentType + "\n    " + blockContent + "\n    // End of automatics"
	return content[:loc[0]] + replacement + content[loc[1]:]
}

// ExpandAutoinput ports expand_autoinput.
func ExpandAutoinput(content, filePath string, proj *Project) string {
	return expandAutoPort(content, filePath, "AUTOINPUT", "input", proj)
}

// ExpandAutooutput ports expand_autooutput.
func ExpandAutooutput(content, filePath string, proj *Project) string {
	return expandAutoPort(content, filePath, "AUTOOUTPUT", "output", proj)
}

// expandAutoSignals ports _expand_auto_signals (AUTOWIRE / AUTOLOGIC): declare
// signals for undeclared nets driven by sub-instance outputs.
func expandAutoSignals(content, filePath, tagName, signalType string, proj *Project) string {
	re := regexp.MustCompile(`(?is)(/\*` + tagName + `\*/)(\s*// Beginning.*?// End of automatics)?`)
	loc := re.FindStringSubmatchIndex(content)
	if loc == nil {
		return content
	}
	tag := content[loc[2]:loc[3]]
	existingBlock := ""
	if loc[4] >= 0 {
		existingBlock = content[loc[4]:loc[5]]
	}
	contentForSignals := content
	if existingBlock != "" {
		contentForSignals = strings.Replace(content, existingBlock, "", 1)
	}
	insts := GetInstantiations(content)
	newSignals := collectAutoDecls(contentForSignals, insts, "output", signalType, true, proj)
	if len(newSignals) == 0 {
		return content[:loc[0]] + tag + content[loc[1]:]
	}
	commentType := "wires"
	if signalType != "wire" {
		commentType = "logic"
	}
	// NB: Python emits a trailing space after the comment type ("wires \n").
	replacement := "/*" + tagName + "*/\n    // Beginning of automatic " + commentType + " \n    " +
		strings.Join(newSignals, "\n    ") + "\n    // End of automatics"
	return content[:loc[0]] + replacement + content[loc[1]:]
}

// ExpandAutowire ports expand_autowire.
func ExpandAutowire(content, filePath string, proj *Project) string {
	return expandAutoSignals(content, filePath, "AUTOWIRE", "wire", proj)
}

// ExpandAutologic ports expand_autologic.
func ExpandAutologic(content, filePath string, proj *Project) string {
	return expandAutoSignals(content, filePath, "AUTOLOGIC", "logic", proj)
}
