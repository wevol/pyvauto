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

type Inst struct {
	ModuleName   string
	InstanceName string
	Ports        map[string]string // port name -> connection expr
}
