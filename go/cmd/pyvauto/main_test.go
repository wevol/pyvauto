package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

// buildBinary compiles the pyvauto binary and returns the path to it.
// It locates the module root (go/) by walking two directories up from this
// test file's source path, which is stable regardless of the working directory
// that `go test` happens to use.
func buildBinary(t *testing.T) string {
	t.Helper()
	_, thisFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}
	// thisFile is .../go/cmd/pyvauto/main_test.go
	// module root is two directories up: .../go/
	moduleRoot := filepath.Join(filepath.Dir(thisFile), "..", "..")

	bin := filepath.Join(t.TempDir(), "pyvauto")
	cmd := exec.Command("go", "build", "-o", bin, "./cmd/pyvauto")
	cmd.Dir = moduleRoot
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("build failed: %v\n%s", err, out)
	}
	return bin
}

func TestCLINoTagsUnchanged(t *testing.T) {
	dir := t.TempDir()
	f := filepath.Join(dir, "m.sv")
	src := "module m;\nendmodule\n"
	os.WriteFile(f, []byte(src), 0644)

	bin := buildBinary(t)
	cmd := exec.Command(bin, f)
	if out, err := cmd.CombinedOutput(); err != nil {
		t.Fatalf("run failed: %v\n%s", err, out)
	}
	got, _ := os.ReadFile(f)
	if string(got) != src {
		t.Fatalf("file changed unexpectedly:\n%s", got)
	}
}

func TestCLIExpandsInstAndArg(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "sub.v"),
		[]byte("module sub(input clk, output [7:0] q);\nendmodule\n"), 0644)
	top := filepath.Join(dir, "top.sv")
	os.WriteFile(top, []byte("module top (/*AUTOARG*/);\n sub u (/*AUTOINST*/);\nendmodule\n"), 0644)

	bin := buildBinary(t)
	if out, err := exec.Command(bin, top).CombinedOutput(); err != nil {
		t.Fatalf("run: %v\n%s", err, out)
	}
	got, _ := os.ReadFile(top)
	s := string(got)
	for _, want := range []string{".clk", ".q", "// Outputs", "// Inputs"} {
		if !strings.Contains(s, want) {
			t.Fatalf("missing %q in AUTOINST output:\n%s", want, s)
		}
	}
	// AUTOARG picked up the ports too (clk/q appear in the header list).
	if !strings.Contains(s, "clk") || !strings.Contains(s, "q") {
		t.Fatalf("AUTOARG not filled:\n%s", s)
	}
}

func TestCLIIncdirFindsSubmodule(t *testing.T) {
	dir := t.TempDir()
	proj := filepath.Join(dir, "proj")
	lib := filepath.Join(dir, "lib")
	other := filepath.Join(dir, "other")
	for _, d := range []string{proj, lib, other} {
		os.MkdirAll(d, 0755)
	}
	os.WriteFile(filepath.Join(lib, "sub.v"),
		[]byte("module sub(input clk, output done);\nendmodule\n"), 0644)
	top := filepath.Join(proj, "top.sv")
	os.WriteFile(top, []byte("module top;\n sub u (/*AUTOINST*/);\nendmodule\n"), 0644)

	bin := buildBinary(t)

	// Without --incdir: sub is neither in the file's dir nor cwd -> not found.
	c1 := exec.Command(bin, top)
	c1.Dir = other
	c1.CombinedOutput()
	if b, _ := os.ReadFile(top); strings.Contains(string(b), ".clk") {
		t.Fatalf("sub should not resolve without --incdir:\n%s", b)
	}

	// With --incdir lib: found.
	c2 := exec.Command(bin, "--incdir", lib, top)
	c2.Dir = other
	if out, err := c2.CombinedOutput(); err != nil {
		t.Fatalf("run: %v\n%s", err, out)
	}
	if b, _ := os.ReadFile(top); !strings.Contains(string(b), ".clk") {
		t.Fatalf("sub should resolve with --incdir:\n%s", b)
	}
}
