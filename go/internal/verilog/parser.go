package verilog

import (
	"regexp"
	"strings"
)

// stripCommentsRe ports pyvauto.py's _STRIP_COMMENTS_RE: match a string literal
// (kept) OR a // line comment OR a /* */ block comment (removed).
var stripCommentsRe = regexp.MustCompile(`(?s)"(?:\\.|[^"\\])*"|//[^\n]*|/\*.*?\*/`)

// StripComments removes // and /* */ comments while preserving string literals.
func StripComments(s string) string {
	return stripCommentsRe.ReplaceAllStringFunc(s, func(m string) string {
		if strings.HasPrefix(m, `"`) {
			return m
		}
		return ""
	})
}

// moduleRe ports pyvauto.py's module_re (re.MULTILINE + re.DOTALL -> (?ms)).
// Groups: 1=name, 2=param block, 3=port block.
var moduleRe = regexp.MustCompile(`(?ms)^[\t ]*module\s+(\w+)\s*(#\s*\(.*?\))?\s*\((.*?)\)\s*;`)

var endmoduleRe = regexp.MustCompile(`\bendmodule\b`)

// portHeadRe matches the leading part of a port declaration: direction, an
// optional type, an optional bus width, and the FIRST name. RE2 has no
// lookahead, so the trailing comma-separated names sharing this declaration are
// collected by hand (see parsePortsFrom) instead of in the regex.
// `\b\s*` after the direction and after the type keyword (and `\s*` after the
// width) tolerate the no-space forms `input[7:0] x` and `input wire[7:0] x`; the
// `\b`s still reject identifiers such as `inputxyz` / `wireless`.
var portHeadRe = regexp.MustCompile(`(input|output|inout)\b\s*(?:(logic|reg|wire)\b\s*)?(?:(\[[^\]]*\])\s*)?(\w+)`)

// contNameRe matches ", <name>" continuing a shared-direction port declaration.
var contNameRe = regexp.MustCompile(`^\s*,\s*(\w+)`)

func isDirectionKeyword(s string) bool {
	return s == "input" || s == "output" || s == "inout"
}

// parsePortsFrom extracts ports from a chunk of (comment-stripped) text —
// either an ANSI header port block or a module body.
func parsePortsFrom(text string) []Port {
	var ports []Port
	for _, loc := range portHeadRe.FindAllStringSubmatchIndex(text, -1) {
		dir := text[loc[2]:loc[3]]
		typ := ""
		if loc[4] >= 0 {
			typ = text[loc[4]:loc[5]]
		}
		width := ""
		if loc[6] >= 0 {
			width = text[loc[6]:loc[7]]
		}
		names := []string{text[loc[8]:loc[9]]}

		// Hand-scan the comma list: keep consuming ", <name>" while <name> is
		// not a direction keyword (which would start a new declaration). This
		// reproduces the Python port_re's negative lookahead, which RE2 lacks.
		pos := loc[1]
		for {
			m := contNameRe.FindStringSubmatchIndex(text[pos:])
			if m == nil {
				break
			}
			name := text[pos+m[2] : pos+m[3]]
			if isDirectionKeyword(name) {
				break
			}
			names = append(names, name)
			pos += m[1]
		}

		if typ == "" {
			typ = "wire"
		}
		for _, n := range names {
			ports = append(ports, Port{Name: n, Direction: dir, Type: typ, Width: width})
		}
	}
	return ports
}

func hasPort(ports []Port, name string) bool {
	for _, p := range ports {
		if p.Name == name {
			return true
		}
	}
	return false
}

// ParseModules parses Verilog content into modules, mirroring
// RegexVerilogParser.parse_file: ANSI header ports first, then body (non-ANSI)
// ports de-duplicated by name.
func ParseModules(content string) []Module {
	c := StripComments(content)
	var mods []Module
	for _, loc := range moduleRe.FindAllStringSubmatchIndex(c, -1) {
		m := Module{Name: c[loc[2]:loc[3]]}

		portBlock := ""
		if loc[6] >= 0 {
			portBlock = c[loc[6]:loc[7]]
		}
		m.Ports = append(m.Ports, parsePortsFrom(portBlock)...)

		body := ""
		if idx := endmoduleRe.FindStringIndex(c[loc[1]:]); idx != nil {
			body = c[loc[1] : loc[1]+idx[0]]
		}
		for _, p := range parsePortsFrom(body) {
			if !hasPort(m.Ports, p.Name) {
				m.Ports = append(m.Ports, p)
			}
		}

		mods = append(mods, m)
	}
	return mods
}

// namedPortConnRe ports _NAMED_PORT_RE (`\.(\w+)\s*\(`), anchored per position.
var namedPortConnRe = regexp.MustCompile(`^\.(\w+)\s*\(`)

// ParseNamedPortConnections parses `.name(value)` pairs in source order,
// depth-counting parens so nested `(...)`/`{...}` in the value are captured
// whole (ports parse_named_port_connections; Python returns an insertion-ordered
// dict, so order is preserved here).
func ParseNamedPortConnections(block string) []PortConn {
	var conns []PortConn
	n := len(block)
	i := 0
	for i < n {
		if block[i] != '.' {
			i++
			continue
		}
		m := namedPortConnRe.FindStringSubmatchIndex(block[i:])
		if m == nil {
			i++
			continue
		}
		name := block[i+m[2] : i+m[3]]
		start := i + m[1] // just past the '('
		j := start
		depth := 1
		for j < n && depth > 0 {
			switch block[j] {
			case '(':
				depth++
			case ')':
				depth--
			}
			j++
		}
		if depth != 0 {
			break
		}
		conns = append(conns, PortConn{Name: name, Signal: strings.TrimSpace(block[start : j-1])})
		i = j
	}
	return conns
}

// connMap collapses ordered connections into a name->signal map (last wins,
// like a Python dict).
func connMap(conns []PortConn) map[string]string {
	m := make(map[string]string, len(conns))
	for _, c := range conns {
		m[c.Name] = c.Signal
	}
	return m
}

var instRe = regexp.MustCompile(`(?s)(\w+)\s+(\w+)\s*(#\s*\(.*?\))?\s*\(([^;]*?)\)\s*;`)

// instSkipKeywords ports _INST_SKIP_KEYWORDS.
var instSkipKeywords = map[string]bool{
	"module": true, "if": true, "always": true, "initial": true, "case": true,
	"generate": true, "assign": true, "begin": true, "endmodule": true,
	"function": true, "task": true,
}

// GetInstantiations extracts module instantiations (ports get_instantiations),
// skipping Verilog keywords and comment-masked text.
func GetInstantiations(content string) []Inst {
	c := StripComments(content)
	var insts []Inst
	for _, mm := range instRe.FindAllStringSubmatch(c, -1) {
		modName := mm[1]
		if instSkipKeywords[modName] {
			continue
		}
		insts = append(insts, Inst{
			ModuleName:   modName,
			InstanceName: mm[2],
			Ports:        ParseNamedPortConnections(mm[4]),
		})
	}
	return insts
}
