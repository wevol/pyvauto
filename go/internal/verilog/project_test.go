package verilog

import (
	"os"
	"path/filepath"
	"testing"
)

func TestResolveSearchesRoots(t *testing.T) {
	dir := t.TempDir()
	a := filepath.Join(dir, "a")
	b := filepath.Join(dir, "b")
	c := filepath.Join(dir, "c")
	for _, d := range []string{a, b, c} {
		if err := os.MkdirAll(d, 0755); err != nil {
			t.Fatal(err)
		}
	}
	os.WriteFile(filepath.Join(b, "sub.v"), []byte("module sub(input clk);\nendmodule\n"), 0644)
	os.WriteFile(filepath.Join(c, "decoy.v"), []byte("module decoy(input x);\nendmodule\n"), 0644)

	p := NewProject()
	p.Resolve([]string{a, b}, map[string]bool{"sub": true})
	if p.Modules["sub"] == nil {
		t.Fatalf("sub not resolved")
	}
	if p.Modules["decoy"] != nil {
		t.Fatalf("decoy in dir c should not be indexed (not a root)")
	}
}

func TestResolveEmptyNeededParsesNothing(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "sub.v"), []byte("module sub(input clk);\nendmodule\n"), 0644)
	p := NewProject()
	p.Resolve([]string{dir}, map[string]bool{})
	if len(p.Modules) != 0 {
		t.Fatalf("expected no modules, got %v", p.Modules)
	}
}
