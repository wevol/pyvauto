module sub (input clk, input rst_n, input [7:0] data_i, output done);
endmodule

module m (input clk, /*AUTOINPUT*/, output done);
    sub u (.clk(clk), .rst_n(rst_n), .data_i(data_i), .done(done));
endmodule
