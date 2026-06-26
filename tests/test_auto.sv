module test_auto  (
    clk,
    rst_n,
    i_data_0,
    o_data_0,
    w_internal
);

    input rst_n;
    input clk;

    /*AUTOINPUT*/
    input [WIDTH-1:0] i_data_0;
    input [WIDTH-1:0] data_i;
    /*AUTOOUTPUT*/
    output [WIDTH-1:0] o_data_0;
    output [WIDTH-1:0] data_o;
    /*AUTOWIRE*/

    // u_sub0: data_i is undeclared -> should be AUTOINPUT
    //         data_o is undeclared -> should be AUTOOUTPUT
    sub_module u_sub0 (
        .clk(clk),
        .rst_n(rst_n),
        .data_i(i_data_0),
        .data_o(o_data_0)
    );

    sub_module u_sub1  (
        .clk   (clk),
        .rst_n (rst_n),
        .data_i(data_i),
        .data_o(data_o)
    );

endmodule
