package verilog

import (
	"regexp"
	"strings"
)

var autoSignalBlockRe = regexp.MustCompile(`(?is)(/\*(?:AUTOWIRE|AUTOLOGIC|AUTOINPUT|AUTOOUTPUT)\*/)\s*// Beginning.*?// End of automatics`)

// DeleteAll ports delete_all: per module block, reverse every AUTO expansion,
// leaving the bare tags.
func DeleteAll(content, filePath string) string {
	return perModuleBlock(content, func(block string) string {
		block = deleteAutoinst(block)
		block = autoSignalBlockRe.ReplaceAllString(block, "$1")
		block = deleteAutosense(block)
		block = deleteHeaderTag(block, "AUTOARG")
		return block
	})
}

// deleteAutoinst ports _delete_autoinst.
func deleteAutoinst(content string) string {
	locs := autoinstRe.FindAllStringSubmatchIndex(content, -1)
	if locs == nil {
		return content
	}
	var b strings.Builder
	last := 0
	for _, loc := range locs {
		b.WriteString(content[last:loc[0]])
		full := content[loc[0]:loc[1]]
		modName := content[loc[2]:loc[3]]
		portBlock := content[loc[8]:loc[9]]
		tag := content[loc[10]:loc[11]]
		if instSkipKeywords[modName] {
			b.WriteString(full)
			last = loc[1]
			continue
		}
		tagEnd := strings.Index(portBlock, tag) + len(tag)
		after := portBlock[tagEnd:]
		trailing := ""
		if idx := strings.LastIndex(after, "\n"); idx != -1 {
			trailing = after[idx:]
		}
		newBlock := portBlock[:tagEnd] + trailing
		b.WriteString(strings.Replace(full, portBlock, newBlock, 1))
		last = loc[1]
	}
	b.WriteString(content[last:])
	return b.String()
}

// deleteAutosense ports _delete_autosense.
func deleteAutosense(content string) string {
	locs := autosenseRe.FindAllStringSubmatchIndex(content, -1)
	if locs == nil {
		return content
	}
	var b strings.Builder
	last := 0
	tag := "/*AUTOSENSE*/"
	for _, loc := range locs {
		b.WriteString(content[last:loc[0]])
		prefix := content[loc[2]:loc[3]]
		paren := content[loc[4]:loc[5]]
		newParen := paren[:strings.Index(paren, tag)] + tag
		b.WriteString(prefix + "(" + newParen + ")")
		last = loc[1]
	}
	b.WriteString(content[last:])
	return b.String()
}

// deleteHeaderTag ports _delete_header_tag (AUTOARG etc.).
func deleteHeaderTag(content, tagName string) string {
	re := regexp.MustCompile(`(?is)(\bmodule\s+(\w+)\s*)(#\s*\(.*?\))?\s*\(([^;]*?(/\*` + tagName + `\*/)[^;]*?)\)\s*;`)
	loc := re.FindStringSubmatchIndex(content)
	if loc == nil {
		return content
	}
	modStart := content[loc[2]:loc[3]]
	params := ""
	if loc[6] >= 0 {
		params = content[loc[6]:loc[7]]
	}
	portBlock := content[loc[8]:loc[9]]
	tag := content[loc[10]:loc[11]]
	head := portBlock[:strings.Index(portBlock, tag)]
	newPortBlock := pyRStrip(head + tag)
	header := pyRStrip(modStart)
	if params != "" {
		header += " " + pyStrip(params)
	}
	return content[:loc[0]] + header + " (" + newPortBlock + "\n);" + content[loc[1]:]
}
