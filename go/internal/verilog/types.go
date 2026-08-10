// Package verilog parses Verilog/SystemVerilog sources and expands (or
// deletes) Emacs verilog-mode AUTO tags, mirroring the behaviour of the
// reference Python implementation in pyvauto.py.
package verilog

type Port struct {
	Name      string
	Direction string // "input" | "output" | "inout"
	Type      string // "wire" default
	Width     string // e.g. "[7:0]" or ""
}

type Module struct {
	Name  string
	Ports []Port
}

// PortConn is one `.name(signal)` connection, kept in source order.
type PortConn struct {
	Name   string
	Signal string
}

type Inst struct {
	ModuleName   string
	InstanceName string
	Ports        []PortConn // in source order (Python dict insertion order)
}
