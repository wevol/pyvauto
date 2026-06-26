module top_autowire (
    input clk,
    input rst_n,
    input [7:0] data_in,
    output [7:0] data_out
);

    /*AUTOWIRE*/
    // Beginning of automatic wires (for undeclared instantiated-module outputs)
    wire [WIDTH-1:0] data_o;
    wire [WIDTH-1:0] w_data_inter;
    // End of automatics

    sub_module u_sub0  (
        .clk   (clk),
        .rst_n (rst_n),
        .data_i(data_i),
        .data_o(data_o)
    );

    sub_module u_sub1 (
        .clk(clk),
        .rst_n(rst_n),
        .data_i(data_in),
        .data_o(w_data_inter)
    );

endmodule
