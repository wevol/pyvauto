package verilog

import (
	"regexp"
	"strings"
	"unicode"
)

// ExpandAll applies the MVP expanders (AUTOINST then AUTOARG) in the same
// relative order as pyvauto.py's expand_all. Tasks 6-7 fill AUTOINST in.
func ExpandAll(content, filePath string, proj *Project) string {
	return content
}

// --- small string helpers matching Python str.strip/lstrip/rstrip ---

func pyStrip(s string) string  { return strings.TrimFunc(s, unicode.IsSpace) }
func pyLStrip(s string) string { return strings.TrimLeftFunc(s, unicode.IsSpace) }
func pyRStrip(s string) string { return strings.TrimRightFunc(s, unicode.IsSpace) }

// applyCommaContext ports _apply_comma_context.
func applyCommaContext(block, before, after string) string {
	if pyStrip(block) == "" {
		return block
	}
	if before != "" && !strings.HasSuffix(before, ",") {
		block = ", " + pyLStrip(block)
	}
	if after != "" && !(strings.HasSuffix(pyRStrip(block), ",") || strings.HasPrefix(after, ",")) {
		block = pyRStrip(block) + ","
	}
	return block
}

// wrapNames ports _wrap_names: comma-separated names wrapped to `limit` columns.
func wrapNames(items []string, indent string, limit int) string {
	var lines []string
	curr := indent
	for i, item := range items {
		suffix := ","
		if i == len(items)-1 {
			suffix = ""
		}
		toAdd := item + suffix
		if i > 0 && len(curr)+len(toAdd)+1 > limit {
			lines = append(lines, pyRStrip(curr))
			curr = indent + toAdd
		} else {
			if i > 0 {
				curr += " "
			}
			curr += toAdd
		}
	}
	if pyStrip(curr) != "" {
		lines = append(lines, pyRStrip(curr))
	}
	return strings.Join(lines, "\n")
}

// formatAutoargList ports _format_autoarg_list.
func formatAutoargList(ports []Port, isANSI bool) string {
	if len(ports) == 0 {
		return ""
	}
	if isANSI {
		var decls []string
		for _, p := range ports {
			w := ""
			if p.Width != "" {
				w = p.Width + " "
			}
			decls = append(decls, p.Direction+" "+w+p.Name)
		}
		return strings.Join(decls, ",\n    ")
	}

	type group struct {
		header string
		names  []string
	}
	var groups []group
	for _, dh := range []struct{ dir, header string }{
		{"output", "    // Outputs"},
		{"inout", "    // Inouts"},
		{"input", "    // Inputs"},
	} {
		var members []string
		for _, p := range ports {
			if p.Direction == dh.dir {
				members = append(members, p.Name)
			}
		}
		if len(members) > 0 {
			groups = append(groups, group{dh.header, members})
		}
	}
	var others []string
	for _, p := range ports {
		if p.Direction != "output" && p.Direction != "inout" && p.Direction != "input" {
			others = append(others, p.Name)
		}
	}
	if len(others) > 0 {
		groups = append(groups, group{"", others})
	}

	var lines []string
	for gi, g := range groups {
		if g.header != "" {
			lines = append(lines, g.header)
		}
		block := wrapNames(g.names, "    ", 80)
		if gi != len(groups)-1 {
			block += ","
		}
		lines = append(lines, block)
	}
	return pyLStrip(strings.Join(lines, "\n"))
}

// collectHeaderPorts ports _collect_header_ports (before-tag region).
func collectHeaderPorts(beforeTag string, isANSI bool) map[string]bool {
	existing := map[string]bool{}
	if isANSI {
		for _, p := range parsePortsFrom(StripComments(beforeTag)) {
			existing[p.Name] = true
		}
	} else {
		for _, part := range strings.Split(StripComments(beforeTag), ",") {
			if name := pyStrip(part); name != "" {
				existing[name] = true
			}
		}
	}
	return existing
}

var autoargRe = regexp.MustCompile(`(?is)(\bmodule\s+(\w+)\s*)(#\s*\(.*?\))?\s*\(([^;]*?(/\*AUTOARG\*/)[^;]*?)\)\s*;`)
var directionInBlockRe = regexp.MustCompile(`\b(input|output|inout)\b`)
var trailingCommaRe = regexp.MustCompile(`,(\s*)$`)

// ExpandAutoarg ports expand_autoarg (Emacs model + direction grouping).
func ExpandAutoarg(content, filePath string, proj *Project) string {
	loc := autoargRe.FindStringSubmatchIndex(content)
	if loc == nil {
		return content
	}
	modStart := content[loc[2]:loc[3]]
	modName := content[loc[4]:loc[5]]
	params := ""
	if loc[6] >= 0 {
		params = content[loc[6]:loc[7]]
	}
	portBlock := content[loc[8]:loc[9]]
	tag := content[loc[10]:loc[11]]

	var module *Module
	for _, m := range ParseModules(content) {
		if m.Name == modName {
			mm := m
			module = &mm
			break
		}
	}
	if module == nil || len(module.Ports) == 0 {
		// Preserve the tag if no ports found.
		kept := strings.Replace(content[loc[0]:loc[1]], tag, "/*AUTOARG*/", 1)
		return content[:loc[0]] + kept + content[loc[1]:]
	}

	tagIndex := strings.Index(portBlock, tag)
	beforeTag := pyStrip(portBlock[:tagIndex])
	isANSI := directionInBlockRe.MatchString(beforeTag)
	existing := collectHeaderPorts(beforeTag, isANSI)

	var toExpand []Port
	for _, p := range module.Ports {
		if !existing[p.Name] {
			toExpand = append(toExpand, p)
		}
	}
	argList := formatAutoargList(toExpand, isANSI)
	argList = applyCommaContext(argList, beforeTag, "")

	var tagWithArgs string
	if pyStrip(argList) != "" {
		tagWithArgs = "/*AUTOARG*/\n    " + argList
	} else {
		tagWithArgs = "/*AUTOARG*/"
	}

	newPortBlock := tagWithArgs
	if beforeTag != "" {
		newPortBlock = beforeTag + " " + tagWithArgs
	}
	newPortBlock = trailingCommaRe.ReplaceAllString(newPortBlock, "$1")

	header := pyRStrip(modStart)
	if params != "" {
		header += " " + pyStrip(params)
	}
	replacement := header + " (" + pyRStrip(newPortBlock) + "\n);"
	return content[:loc[0]] + replacement + content[loc[1]:]
}
