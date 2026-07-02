package main

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/wevol/pyvauto/go/internal/verilog"
)

func main() {
	var incdirs []string
	var files []string
	deleteMode := false

	args := os.Args[1:]
	for i := 0; i < len(args); i++ {
		a := args[i]
		switch {
		case a == "--delete" || a == "-k":
			deleteMode = true
		case a == "--incdir":
			if i+1 >= len(args) {
				fmt.Fprintln(os.Stderr, "--incdir requires a directory")
				os.Exit(2)
			}
			i++
			incdirs = append(incdirs, args[i])
		default:
			files = append(files, a)
		}
	}

	if deleteMode {
		fmt.Fprintln(os.Stderr, "--delete is not implemented in the Go MVP")
		os.Exit(2)
	}
	if len(files) == 0 {
		fmt.Fprintln(os.Stderr, "usage: pyvauto [--incdir DIR]... <file>...")
		os.Exit(2)
	}

	for _, fpath := range files {
		if _, err := os.Stat(fpath); err != nil {
			fmt.Printf("Skip: %s (not found)\n", fpath)
			continue
		}
		content, err := os.ReadFile(fpath)
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		// Resolve only the sub-modules this file instantiates, searching the
		// file's own directory plus any --incdir dirs.
		proj := verilog.NewProject()
		needed := map[string]bool{}
		for _, inst := range verilog.GetInstantiations(string(content)) {
			needed[inst.ModuleName] = true
		}
		roots := append([]string{filepath.Dir(fpath)}, incdirs...)
		proj.Resolve(roots, needed)

		out := verilog.ExpandAll(string(content), fpath, proj)
		if out != string(content) {
			if err := os.WriteFile(fpath, []byte(out), 0644); err != nil {
				fmt.Fprintln(os.Stderr, err)
				os.Exit(1)
			}
			fmt.Printf("Successfully expanded %s\n", fpath)
		} else {
			fmt.Printf("No changes made to %s\n", fpath)
		}
	}
}
