// Mixed-mode (non-ANSI): manual declarations coexist with AUTO* tags.
// Port list carries names only (AUTOARG); directions live in the body.
module mixed_top (
    /*AUTOARG*/
);

    input clk;
    output manual_out;

    /*AUTOINPUT*/
    /*AUTOOUTPUT*/

    sub_module u_sub0 (
        .clk(clk),
        .data_i(auto_in_from_sub),
        .data_o(auto_out_from_sub)
    );

endmodule
