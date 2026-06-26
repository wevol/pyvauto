module mixed_top (
    /*autoarg*/
    input clk,
);

    /*AUTOOUTPUT*/
    output manual_out;

    sub_module u_sub0 (
        .clk(clk),
        .data_i(auto_in_from_sub),
        .data_o(auto_out_from_sub)
    );

endmodule
