package verilog

import (
	"regexp"
	"strings"
	"unicode"
)

// moduleBlockRe ports _MODULE_BLOCK_RE.
var moduleBlockRe = regexp.MustCompile(`(?ims)^[\t ]*module\s+\w+.*?\bendmodule\b`)

// perModuleBlock applies fn to each module…endmodule block (ports
// _per_module_block).
func perModuleBlock(content string, fn func(string) string) string {
	return moduleBlockRe.ReplaceAllStringFunc(content, fn)
}

// ExpandAll applies the expanders per module block in pyvauto.py's expand_all
// order. (AUTOINPUT/OUTPUT/WIRE/LOGIC/SENSE are inserted by later tasks.)
func ExpandAll(content, filePath string, proj *Project) string {
	return perModuleBlock(content, func(block string) string {
		block = ExpandAutoinst(block, filePath, proj)
		block = ExpandAutoinput(block, filePath, proj)
		block = ExpandAutooutput(block, filePath, proj)
		block = ExpandAutowire(block, filePath, proj)
		block = ExpandAutologic(block, filePath, proj)
		block = ExpandAutosense(block, filePath, proj)
		block = ExpandAutoarg(block, filePath, proj)
		return block
	})
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

var autoinstRe = regexp.MustCompile(`(?is)(\w+)\s+(\w+)\s*(#\s*\(.*?\))?\s*\(([^;]*?(/\*AUTOINST\*/)[^;]*?)\)\s*;`)
var doubleCommaRe = regexp.MustCompile(`,(\s*),`)
var reconcileSignalRe = regexp.MustCompile(`^\s*(\w+)\s*(\[[^\]]*\])?\s*$`)

// reconcileSignal ports _reconcile_signal: reuse a simple identifier's base and
// refresh its width; leave complex expressions verbatim.
func reconcileSignal(existing, width string) string {
	m := reconcileSignalRe.FindStringSubmatch(existing)
	if m == nil {
		return existing
	}
	return m[1] + width
}

// buildAutoinstPortLines ports _build_autoinst_port_lines, including the
// width-mismatch warning comment (vs the enclosing module's local signals).
func buildAutoinstPortLines(ports []Port, afterConns map[string]string, modName string, localWidths map[string]string) string {
	var lines []string
	lineWarnings := map[int]string{}
	formatP := func(p Port) string {
		ex, existing := afterConns[p.Name]
		var signal string
		if existing {
			signal = reconcileSignal(ex, p.Width)
		} else {
			signal = p.Name + p.Width
		}
		line := "    ." + p.Name + " (" + signal + ")"
		if !existing {
			localW := localWidths[p.Name]
			if widthsMismatch(p.Width, localW) {
				lineWarnings[len(lines)] = "  // WARNING: width mismatch — " +
					modName + "." + p.Name + " is " + p.Width + ", local " + p.Name + " is " + localW
			}
		}
		return line
	}
	for _, dh := range []struct{ dir, header string }{
		{"output", "    // Outputs"},
		{"inout", "    // Inouts"},
		{"input", "    // Inputs"},
	} {
		var members []Port
		for _, p := range ports {
			if p.Direction == dh.dir {
				members = append(members, p)
			}
		}
		if len(members) > 0 {
			lines = append(lines, dh.header)
			for _, p := range members {
				lines = append(lines, formatP(p))
			}
		}
	}
	for _, p := range ports {
		if p.Direction != "output" && p.Direction != "inout" && p.Direction != "input" {
			lines = append(lines, formatP(p))
		}
	}
	var portIdx []int
	for i, l := range lines {
		if strings.HasPrefix(pyStrip(l), ".") {
			portIdx = append(portIdx, i)
		}
	}
	for k := 0; k+1 < len(portIdx); k++ {
		lines[portIdx[k]] += ","
	}
	for i, w := range lineWarnings {
		lines[i] = lines[i] + w
	}
	return strings.Join(lines, "\n")
}

// ExpandAutoinst ports expand_autoinst (MVP: reconcile against module ports;
// module definitions come from the project index).
func ExpandAutoinst(content, filePath string, proj *Project) string {
	locs := autoinstRe.FindAllStringSubmatchIndex(content, -1)
	if locs == nil {
		return content
	}
	localWidths := getLocalSignalWidths(content)
	var b strings.Builder
	last := 0
	for _, loc := range locs {
		b.WriteString(content[last:loc[0]])
		b.WriteString(autoinstReplace(content, loc, proj, localWidths))
		last = loc[1]
	}
	b.WriteString(content[last:])
	return b.String()
}

func autoinstReplace(content string, loc []int, proj *Project, localWidths map[string]string) string {
	full := content[loc[0]:loc[1]]
	modName := content[loc[2]:loc[3]]
	instName := content[loc[4]:loc[5]]
	param := ""
	if loc[6] >= 0 {
		param = content[loc[6]:loc[7]]
	}
	portBlock := content[loc[8]:loc[9]]
	tag := content[loc[10]:loc[11]]

	if instSkipKeywords[modName] {
		return full
	}
	module := proj.Modules[modName]
	if module == nil {
		return full
	}

	tagIndex := strings.Index(portBlock, tag)
	beforeTag := portBlock[:tagIndex]
	afterTag := portBlock[tagIndex+len(tag):]

	beforeConns := ParseNamedPortConnections(StripComments(beforeTag))
	afterConns := connMap(ParseNamedPortConnections(StripComments(afterTag)))
	claimed := map[string]bool{}
	for _, c := range beforeConns {
		claimed[c.Name] = true
	}

	var portsToEmit []Port
	for _, p := range module.Ports {
		if !claimed[p.Name] {
			portsToEmit = append(portsToEmit, p)
		}
	}
	portStr := buildAutoinstPortLines(portsToEmit, afterConns, modName, localWidths)

	beforeStripped := pyStrip(beforeTag)
	var newPortBlock string
	if pyStrip(portStr) != "" {
		portStr = applyCommaContext(portStr, beforeStripped, "")
		newPortBlock = beforeTag + "/*AUTOINST*/\n" + portStr
	} else {
		newPortBlock = beforeTag + "/*AUTOINST*/"
	}
	newPortBlock = trailingCommaRe.ReplaceAllString(newPortBlock, "$1")
	newPortBlock = doubleCommaRe.ReplaceAllString(newPortBlock, ",$1")

	return modName + " " + instName + " " + param + " (" + newPortBlock + "\n    );"
}
