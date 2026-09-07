#!/bin/sh

output=lex.yy.c
expect_output=false

for argument do
  if [ "$expect_output" = true ]; then
    output=$argument
    expect_output=false
    continue
  fi
  case "$argument" in
    -o|--outfile)
      expect_output=true
      ;;
    -o*)
      output=${argument#-o}
      ;;
    --outfile=*)
      output=${argument#--outfile=}
      ;;
    --version|-V|--help|-h)
      /usr/local/bin/flex-real "$@"
      return $?
      ;;
  esac
done

raw_output="/tmp/edgeterm-flex-$$.m4"
if ! /usr/local/bin/flex-real "$@" --preproc=0 -o "$raw_output"; then
  rm -f "$raw_output"
  return 1
fi

if [ "$output" = "-" ]; then
  /usr/local/bin/m4 -P "$raw_output"
  status=$?
else
  /usr/local/bin/m4 -P "$raw_output" > "$output"
  status=$?
fi
rm -f "$raw_output"
return "$status"
