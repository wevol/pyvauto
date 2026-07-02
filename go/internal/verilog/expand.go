package verilog

// Project holds the parsed modules discovered from include directories.
// Task 4 fills this with real scanning logic.
type Project struct {
	Modules map[string]*Module
}

func NewProject() *Project { return &Project{Modules: map[string]*Module{}} }

// ExpandAll applies the MVP expanders (AUTOINST then AUTOARG) in the same
// relative order as pyvauto.py's expand_all. Task 1 is an identity stub;
// Tasks 5-6 fill it in.
func ExpandAll(content, filePath string, proj *Project) string {
	return content
}
