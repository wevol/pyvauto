module sub (input clk, input rst_n, input [7:0] data_i, output [7:0] data_o);
endmodule

module top;
    sub u_sub (
        .clk(my_clk),
        /*AUTOINST*/
    );
endmodule
