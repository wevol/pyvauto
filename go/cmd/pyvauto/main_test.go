package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
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
