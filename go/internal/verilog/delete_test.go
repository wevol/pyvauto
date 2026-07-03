package verilog

import (
	"os"
	"path/filepath"
	"testing"
)

// deleteGolden runs DeleteAll on the expanded golden `<name>.golden` and asserts
// byte-equality with the Python-produced `<name>.del.golden`.
func deleteGolden(t *testing.T, name string) {
	t.Helper()
	in, err := os.ReadFile(filepath.Join("..", "..", "testdata", "golden", name+".golden"))
	if err != nil {
		t.Fatal(err)
	}
	want, err := os.ReadFile(filepath.Join("..", "..", "testdata", "golden", name+".del.golden"))
	if err != nil {
		t.Fatal(err)
	}
	got := DeleteAll(string(in), name+".sv")
	if got != string(want) {
		t.Fatalf("delete mismatch for %s\n--- got ---\n%q\n--- want ---\n%q", name, got, string(want))
	}
}

func TestDeleteAutoinst(t *testing.T)  { deleteGolden(t, "autoinst_basic") }
func TestDeleteAutowire(t *testing.T)  { deleteGolden(t, "autowire_basic") }
func TestDeleteAutologic(t *testing.T) { deleteGolden(t, "autologic_mixed") }
func TestDeleteAutosense(t *testing.T) { deleteGolden(t, "autosense_comb") }
func TestDeleteAutoarg(t *testing.T)   { deleteGolden(t, "autoarg_basic") }
func TestDeleteAutoinput(t *testing.T) { deleteGolden(t, "autoinput_body") }

// ANSI header-form AUTOINPUT/AUTOOUTPUT are now reversible: expansion keeps the
// tag + Begin/End markers, so DeleteAll strips them back to the bare tag.
func TestDeleteAutooutputAnsi(t *testing.T) { deleteGolden(t, "autooutput_ansi") }
func TestDeleteAutoinputAnsi(t *testing.T)  { deleteGolden(t, "autoinput_ansi") }
