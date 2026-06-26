module ansi_mixed_arg #(
    parameter WIDTH = 8
) (
    input clk,
    input rst_n,
    input [WIDTH-1:0] data_i,
    output [WIDTH-1:0] data_o

);

    input rst_n;
    input [WIDTH-1:0] data_i;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) data_o <= 0;
        else        data_o <= data_i;
    end

endmodule
