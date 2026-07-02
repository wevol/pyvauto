module sub (input [7:0] data_i, output [7:0] data_o);
endmodule

module top;
    wire [15:0] data_i;
    wire [7:0] data_o;
    sub u (/*AUTOINST*/);
endmodule
