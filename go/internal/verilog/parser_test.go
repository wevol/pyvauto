package verilog

import (
	"reflect"
	"testing"
)

func portNames(m Module) []string {
	out := []string{}
	for _, p := range m.Ports {
		out = append(out, p.Name)
	}
	return out
}

func TestParseSimpleModule(t *testing.T) {
	src := "module simple (\n input clk,\n input rst_n,\n output [7:0] data_out\n);\nendmodule\n"
	mods := ParseModules(src)
	if len(mods) != 1 || mods[0].Name != "simple" {
		t.Fatalf("bad modules: %+v", mods)
	}
	if got := portNames(mods[0]); !reflect.DeepEqual(got, []string{"clk", "rst_n", "data_out"}) {
		t.Fatalf("ports = %v", got)
	}
	by := map[string]Port{}
	for _, p := range mods[0].Ports {
		by[p.Name] = p
	}
	if by["data_out"].Width != "[7:0]" {
		t.Fatalf("data_out width = %q", by["data_out"].Width)
	}
	if by["clk"].Direction != "input" || by["data_out"].Direction != "output" {
		t.Fatalf("directions wrong: %+v", by)
	}
}

func TestParsePortsMultipleVarsPerLine(t *testing.T) {
	src := "module marg (/*AUTOARG*/);\n input [3:0] x, y;\n input clk, rst_n, en;\nendmodule\n"
	mods := ParseModules(src)
	got := portNames(mods[0])
	want := []string{"x", "y", "clk", "rst_n", "en"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("ports = %v want %v", got, want)
	}
	by := map[string]Port{}
	for _, p := range mods[0].Ports {
		by[p.Name] = p
	}
	if by["y"].Width != "[3:0]" {
		t.Fatalf("y width = %q (should share the [3:0] of the line)", by["y"].Width)
	}
}

func TestParsePortsAnsiRepeatedDirectionNotMerged(t *testing.T) {
	src := "module m (input a, input b, output c);\nendmodule\n"
	got := portNames(ParseModules(src)[0])
	if !reflect.DeepEqual(got, []string{"a", "b", "c"}) {
		t.Fatalf("ports = %v", got)
	}
}

func TestParsePortsAnsiSharedDirectionCommaList(t *testing.T) {
	src := "module m (input a, b, output c, d);\nendmodule\n"
	got := portNames(ParseModules(src)[0])
	if !reflect.DeepEqual(got, []string{"a", "b", "c", "d"}) {
		t.Fatalf("ports = %v", got)
	}
}

func TestStripCommentsPreservesStrings(t *testing.T) {
	src := `x = "http://a /* b */"; // c`
	out := StripComments(src)
	if got := out; got != `x = "http://a /* b */"; ` {
		t.Fatalf("strip = %q", got)
	}
}
