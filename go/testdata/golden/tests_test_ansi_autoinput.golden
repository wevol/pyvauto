module ansi_top  (
    input clk,
    input rst_n,
    input [WIDTH-1:0] auto_in_from_sub,
    output data_out

);

    sub_module u_sub (
        .clk(clk),
        .rst_n(rst_n),
        .data_i(auto_in_from_sub),
        .data_o(data_out)
    );

endmodule
