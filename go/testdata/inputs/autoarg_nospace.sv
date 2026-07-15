module m (/*AUTOARG*/);
    input clk;
    input[7:0] data_in;
    output[3:0] data_out;
    input wire[7:0] w_in;
    output reg[3:0] r_out;
    inout bus;
endmodule
