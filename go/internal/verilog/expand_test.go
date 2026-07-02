package verilog

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestExpandAllPerModuleBlock(t *testing.T) {
	src := "module a (/*AUTOARG*/);\n input x;\n output y;\nendmodule\n\n" +
		"module b (/*AUTOARG*/);\n input p;\n output q;\nendmodule\n"
	got := ExpandAll(src, "m.sv", NewProject())
	if n := strings.Count(got, "// Inputs"); n != 2 {
		t.Fatalf("expected both modules expanded (2 // Inputs), got %d:\n%s", n, got)
	}
	if !strings.Contains(got, "x") || !strings.Contains(got, "q") {
		t.Fatalf("ports missing:\n%s", got)
	}
}

func runGolden(t *testing.T, name string, expand func(string, string, *Project) string) {
	t.Helper()
	in, err := os.ReadFile(filepath.Join("..", "..", "testdata", "inputs", name+".sv"))
	if err != nil {
		t.Fatal(err)
	}
	want, err := os.ReadFile(filepath.Join("..", "..", "testdata", "golden", name+".golden"))
	if err != nil {
		t.Fatal(err)
	}
	got := expand(string(in), name+".sv", NewProject())
	if got != string(want) {
		t.Fatalf("golden mismatch for %s\n--- got ---\n%q\n--- want ---\n%q", name, got, string(want))
	}
}

func TestAutoargGolden(t *testing.T) {
	runGolden(t, "autoarg_basic", ExpandAutoarg)
}

func TestAutoinstGolden(t *testing.T) {
	in, err := os.ReadFile(filepath.Join("..", "..", "testdata", "inputs", "autoinst_basic.sv"))
	if err != nil {
		t.Fatal(err)
	}
	want, err := os.ReadFile(filepath.Join("..", "..", "testdata", "golden", "autoinst_basic.golden"))
	if err != nil {
		t.Fatal(err)
	}
	proj := NewProject()
	for _, m := range ParseModules(string(in)) {
		mm := m
		proj.Modules[mm.Name] = &mm
	}
	got := ExpandAutoinst(string(in), "autoinst_basic.sv", proj)
	if got != string(want) {
		t.Fatalf("mismatch\n--- got ---\n%q\n--- want ---\n%q", got, string(want))
	}
}
