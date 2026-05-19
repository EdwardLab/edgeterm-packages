for dir in packages/*; do
  [ -d "$dir" ] || continue
  name=$(basename "$dir")
  version=$(jq -r '.version' "$dir/package.json")
  tar -czf "$dir/${name}-${version}-edgeterm-wasm32.tar.gz" -C "$dir" .
done