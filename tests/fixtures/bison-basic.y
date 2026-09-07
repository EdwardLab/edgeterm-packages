%token NUMBER
%%
input:
    %empty
  | input NUMBER
  ;
%%
int yyerror(const char *message) { (void)message; return 0; }
