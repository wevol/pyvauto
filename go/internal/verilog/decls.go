package verilog

import (
	"regexp"
	"strings"
)

// typeDeclRe ports _TYPE_DECL_RE.
var typeDeclRe = regexp.MustCompile(`\b(wire|reg|logic|integer|bit|real|byte|shortint|int|longint)\b\s+(\[.*?\]\s+)?([\w\s,]+);`)

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
