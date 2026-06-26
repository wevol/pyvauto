module top_module         (
    /*AUTOARG*/
        data_i2,
        rst_n, data_i,
clk







);

 /*AUTOINPUT*/
    input [4:1] data_i2;
    input clk;
    input rst_n;
    input [WIDTH-1:0] data_i;

    sub_module u_sub  (
        /*AUTOINST*/
        /*output*/
        .data_o (data_o[WIDTH-1:0]),
        /*input*/
        .rst_n (rst_n),
        .data_i (data_i[WIDTH-1:0]),
        .data_i2 (data_i2[4:1]),
       .clk (clk)
    
    
    
    );

endmodule
