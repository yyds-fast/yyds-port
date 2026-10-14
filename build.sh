#!/bin/bash

set -euo pipefail

repository_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$repository_root"

clean=false
upload=false

for option in "$@"; do
    case "$option" in
        --clean)
            clean=true
            ;;
        --upload)
            upload=true
            ;;
        *)
            echo "Usage: $0 [--clean] [--upload]" >&2
            exit 2
            ;;
    esac
done

if [[ "$clean" == true ]]; then
    rm -rf build dist yyds_port.egg-info
fi

package_version="$(python3 -c 'from yyds_port.__version__ import __version__; print(__version__)')"
artifacts=(
    "dist/yyds_port-${package_version}-py3-none-any.whl"
    "dist/yyds_port-${package_version}.tar.gz"
)

python3 -m build
for artifact in "${artifacts[@]}"; do
    if [[ ! -f "$artifact" ]]; then
        echo "Expected build artifact was not created: $artifact" >&2
        exit 1
    fi
done

python3 -m twine check "${artifacts[@]}"

if [[ "$upload" == true ]]; then
    python3 -m twine upload "${artifacts[@]}"
else
    echo "Build verified. Pass --upload to upload the artifacts; use --clean to remove old build outputs first."
fi
