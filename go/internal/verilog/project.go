package verilog

import (
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

// Project holds the parsed modules discovered by Resolve.
type Project struct {
	Modules map[string]*Module
}

func NewProject() *Project { return &Project{Modules: map[string]*Module{}} }

func isVerilogFile(name string) bool {
	return (strings.HasSuffix(name, ".v") || strings.HasSuffix(name, ".sv")) && name != "test_top.sv"
}

// indexFile parses one file and adds its modules to the index.
func (p *Project) indexFile(path string) {
	data, err := os.ReadFile(path)
	if err != nil {
		return
	}
	for _, m := range ParseModules(string(data)) {
		mod := m
		p.Modules[mod.Name] = &mod
	}
}

// Resolve indexes only the modules named in `needed` (plus any co-located in the
// same files), parsing as few files as possible, across one or more root
// directories. Module names are globally unique, so first-found wins. Ports
// pyvauto.py's VerilogProject.resolve.
func (p *Project) Resolve(roots []string, needed map[string]bool) {
	pending := map[string]bool{}
	for n := range needed {
		pending[n] = true
	}
	if len(pending) == 0 {
		return
	}

	// De-duplicate roots by absolute (symlink-resolved) path, preserving order.
	seen := map[string]bool{}
	var uniq []string
	for _, r := range roots {
		abs, err := filepath.Abs(r)
		if err != nil {
			abs = r
		}
		if resolved, err := filepath.EvalSymlinks(abs); err == nil {
			abs = resolved
		}
		if !seen[abs] {
			seen[abs] = true
			uniq = append(uniq, r)
		}
	}

	// One cheap directory listing per root — names only, no parsing.
	var candidates []string
	byBasename := map[string]string{}
	for _, root := range uniq {
		_ = filepath.WalkDir(root, func(path string, d fs.DirEntry, err error) error {
			if err != nil || d.IsDir() {
				return nil
			}
			name := d.Name()
			if isVerilogFile(name) {
				candidates = append(candidates, path)
				base := strings.TrimSuffix(name, filepath.Ext(name))
				if _, ok := byBasename[base]; !ok {
					byBasename[base] = path
				}
			}
			return nil
		})
	}

	parsed := map[string]bool{}
	dropResolved := func() {
		for n := range p.Modules {
			delete(pending, n)
		}
	}

	// Filename fast-path: parse only "<name>.v"/".sv".
	var names []string
	for n := range pending {
		names = append(names, n)
	}
	for _, name := range names {
		if hit, ok := byBasename[name]; ok && !parsed[hit] {
			p.indexFile(hit)
			parsed[hit] = true
			dropResolved()
			if len(pending) == 0 {
				return
			}
		}
	}

	// Early-stop fallback: parse remaining files whose text declares a pending
	// module (a word-boundary "module <name>" pre-filter).
	for _, full := range candidates {
		if len(pending) == 0 {
			return
		}
		if parsed[full] {
			continue
		}
		data, err := os.ReadFile(full)
		if err != nil {
			continue
		}
		if !anyModuleDeclared(string(data), pending) {
			continue
		}
		p.indexFile(full)
		parsed[full] = true
		dropResolved()
	}
}

func anyModuleDeclared(content string, pending map[string]bool) bool {
	if len(pending) == 0 {
		return false
	}
	quoted := make([]string, 0, len(pending))
	for n := range pending {
		quoted = append(quoted, regexp.QuoteMeta(n))
	}
	re := regexp.MustCompile(`\bmodule\s+(?:` + strings.Join(quoted, "|") + `)\b`)
	return re.MatchString(content)
}
