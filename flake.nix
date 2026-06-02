{
  description = "semantic-bts — BSL + xorq demo over BTS On-Time flights, with pi.dev agent integration.";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";

    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      pyproject-nix,
      uv2nix,
      pyproject-build-systems,
      ...
    }:
    let
      inherit (nixpkgs) lib;
      forAllSystems = lib.genAttrs lib.systems.flakeExposed;

      workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };

      overlay = workspace.mkPyprojectOverlay {
        sourcePreference = "wheel";
      };

      editableOverlay = workspace.mkEditablePyprojectOverlay {
        root = "$REPO_ROOT";
      };

      pythonSets = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          python = pkgs.python3;
        in
        (pkgs.callPackage pyproject-nix.build.packages {
          inherit python;
        }).overrideScope
          (
            lib.composeManyExtensions [
              pyproject-build-systems.overlays.wheel
              overlay
            ]
          )
      );

      # pi.dev coding agent bundle — built reproducibly from pi/package-lock.json
      # via buildNpmPackage. The package itself has no build step; we just want
      # its node_modules so we can invoke `pi` from the transitive dependency.
      #
      # First build: set `npmDepsHash = lib.fakeHash` and run `nix build .#pi-bundle`;
      # nix will print the correct hash. Paste it back in.
      piBundles = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        pkgs.buildNpmPackage {
          pname = "semantic-bts-pi";
          version = "0.1.0";
          src = ./pi;
          # Replace with the hash nix prints on first build.
          npmDepsHash = "sha256-L8FKGgqBF6u2yyO9d0kJi6hgnsLgxSHRoh8Jq772jd8=";
          # No build step — pi-coding-agent ships precompiled JS.
          dontNpmBuild = true;
          # Install hook: leave node_modules under $out/lib/node_modules/<pkg>/
          # (the default for buildNpmPackage) and add a `pi` wrapper to $out/bin.
          postInstall = ''
            mkdir -p $out/bin
            # The dependency installs its CLI under node_modules/.bin/pi.
            pkgRoot=$out/lib/node_modules/@xorq-labs/semantic-bts-pi
            ln -s $pkgRoot/node_modules/.bin/pi $out/bin/pi
          '';
          meta.description = "Reproducible pi-coding-agent bundle for semantic-bts";
        }
      );

      # The shared launcher script for `pi` — used by both the devShell (as
      # the canonical entry point on PATH) and `nix run .#pi`.
      #
      # It guarantees:
      #   - COLORTERM=truecolor so pi's TUI renders correctly
      #   - XORQ_CATALOG_PATH points at $REPO_ROOT/xorq-catalog-bts when the
      #     submodule is checked out (so the xorq extension targets it)
      #   - XORQ_BUILDS_DIR points at $REPO_ROOT/builds
      #   - .pi/settings.json (in $REPO_ROOT or a fresh scratch dir) is wired
      #     to the store-path pi bundle so extensions/skills load from /nix/store
      makePiLauncher =
        { pkgs, venv, piBundle }:
        pkgs.writeShellApplication {
          name = "semantic-bts-pi";
          runtimeInputs = [
            piBundle
            venv
            pkgs.nodejs
            pkgs.git
            pkgs.coreutils
          ];
          text = ''
            set -euo pipefail

            # Locate the repo root if we're inside a semantic-bts checkout;
            # otherwise fall back to a scratch dir and clone the catalog so
            # `nix run github:.../#pi` works from /tmp or any unrelated repo.
            REPO_ROOT=""
            if git rev-parse --show-toplevel >/dev/null 2>&1; then
              candidate=$(git rev-parse --show-toplevel)
              # Guard: only treat the cwd as REPO_ROOT if it's actually a
              # semantic-bts checkout (avoids scribbling .pi/, pi/, builds/
              # into an unrelated repo the user happens to be inside).
              if [ -f "$candidate/.gitmodules" ] && \
                 grep -q "xorq-catalog-bts" "$candidate/.gitmodules" 2>/dev/null; then
                REPO_ROOT=$candidate
              else
                echo "[semantic-bts-pi] cwd is a git repo but not semantic-bts — using scratch dir" >&2
              fi
            fi
            if [ -z "$REPO_ROOT" ]; then
              REPO_ROOT=$(mktemp -d -t semantic-bts-pi.XXXXXX)
              echo "[semantic-bts-pi] scratch dir: $REPO_ROOT" >&2
              echo "[semantic-bts-pi] cloning xorq-catalog-bts..." >&2
              git clone --depth=1 \
                https://github.com/xorq-labs/xorq-catalog-bts \
                "$REPO_ROOT/xorq-catalog-bts" >&2
            fi
            export REPO_ROOT

            export COLORTERM=truecolor

            # Point the xorq extension at the pinned project catalog if present.
            if [ -f "$REPO_ROOT/xorq-catalog-bts/catalog.yaml" ]; then
              export XORQ_CATALOG_PATH="$REPO_ROOT/xorq-catalog-bts"
            fi
            export XORQ_BUILDS_DIR="$REPO_ROOT/builds"
            mkdir -p "$XORQ_BUILDS_DIR"

            # Wire up the pi package directory so `.pi/settings.json` →
            # `../pi` resolves. There are two cases:
            #
            #   (a) User is in a clone: pi/ already has extensions/ + skills/
            #       but no node_modules/. Symlink node_modules → /nix/store.
            #
            #   (b) User is outside any clone (scratch dir): no pi/ at all.
            #       Symlink the whole pi/ → /nix/store package dir, and
            #       create a .pi/settings.json pointing at it.
            STORE_PI="${piBundle}/lib/node_modules/@xorq-labs/semantic-bts-pi"
            if [ -d "$REPO_ROOT/pi" ]; then
              if [ ! -e "$REPO_ROOT/pi/node_modules" ]; then
                ln -sfn "$STORE_PI/node_modules" "$REPO_ROOT/pi/node_modules"
              fi
            else
              ln -sfn "$STORE_PI" "$REPO_ROOT/pi"
            fi
            if [ ! -f "$REPO_ROOT/.pi/settings.json" ]; then
              mkdir -p "$REPO_ROOT/.pi"
              printf '{"packages": ["../pi"]}\n' > "$REPO_ROOT/.pi/settings.json"
            fi

            cd "$REPO_ROOT"
            exec pi "$@"
          '';
        };

      # Launcher for `nix run .#tui` — opens the xorq catalog TUI against the
      # bundled BTS catalog. Like the pi launcher, it works with zero clone:
      # if the cwd isn't a semantic-bts checkout it shallow-clones
      # xorq-catalog-bts into a scratch dir and points the TUI at it.
      makeTuiLauncher =
        { pkgs, venv }:
        pkgs.writeShellApplication {
          name = "semantic-bts-tui";
          runtimeInputs = [
            venv
            pkgs.git
            pkgs.coreutils
          ];
          text = ''
            set -euo pipefail

            CATALOG=""
            if git rev-parse --show-toplevel >/dev/null 2>&1; then
              candidate=$(git rev-parse --show-toplevel)
              if [ -f "$candidate/xorq-catalog-bts/catalog.yaml" ]; then
                CATALOG="$candidate/xorq-catalog-bts"
              fi
            fi
            if [ -z "$CATALOG" ]; then
              scratch=$(mktemp -d -t semantic-bts-tui.XXXXXX)
              echo "[semantic-bts-tui] cloning xorq-catalog-bts into $scratch..." >&2
              git clone --depth=1 \
                https://github.com/xorq-labs/xorq-catalog-bts \
                "$scratch/xorq-catalog-bts" >&2
              CATALOG="$scratch/xorq-catalog-bts"
            fi

            exec xorq catalog -p "$CATALOG" tui "$@"
          '';
        };
    in
    {
      devShells = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          pythonSet = pythonSets.${system}.overrideScope editableOverlay;
          virtualenv = pythonSet.mkVirtualEnv "semantic-bts-dev-env" workspace.deps.all;
          piBundle = piBundles.${system};
          piLauncher = makePiLauncher {
            inherit pkgs;
            venv = virtualenv;
            inherit piBundle;
          };
        in
        {
          default = pkgs.mkShell {
            packages = [
              virtualenv
              pkgs.uv
              pkgs.nodejs
              piBundle
              piLauncher
            ];
            env = {
              UV_NO_SYNC = "1";
              UV_PYTHON = pythonSet.python.interpreter;
              UV_PYTHON_DOWNLOADS = "never";
              COLORTERM = "truecolor";
            };
            shellHook = ''
              unset PYTHONPATH
              export REPO_ROOT=$(git rev-parse --show-toplevel)
              # Pin the xorq extension to the submodule catalog.
              if [ -f "$REPO_ROOT/xorq-catalog-bts/catalog.yaml" ]; then
                export XORQ_CATALOG_PATH="$REPO_ROOT/xorq-catalog-bts"
              fi
              export XORQ_BUILDS_DIR="$REPO_ROOT/builds"
              mkdir -p "$XORQ_BUILDS_DIR"

              # Symlink pi/node_modules → /nix/store so .pi/settings.json's
              # `../pi` reference resolves with the reproducibly-built deps.
              STORE_PI="${piBundle}/lib/node_modules/@xorq-labs/semantic-bts-pi"
              if [ -d "$REPO_ROOT/pi" ] && [ ! -e "$REPO_ROOT/pi/node_modules" ]; then
                ln -sfn "$STORE_PI/node_modules" "$REPO_ROOT/pi/node_modules"
              fi

              # `pi` resolves to the launcher (provided by piLauncher in PATH).
              echo "semantic-bts dev shell"
              [ -n "''${XORQ_CATALOG_PATH:-}" ] && \
                echo "  XORQ_CATALOG_PATH = $XORQ_CATALOG_PATH"
              echo "  XORQ_BUILDS_DIR   = $XORQ_BUILDS_DIR"
              echo "  COLORTERM         = $COLORTERM"
              echo "Run \`pi\` to launch the agent."
            '';
          };
        }
      );

      formatter = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        pkgs.nixfmt-tree
      );

      packages = forAllSystems (
        system: {
          default = pythonSets.${system}.mkVirtualEnv "semantic-bts-env" workspace.deps.default;
          pi-bundle = piBundles.${system};
        }
      );

      apps = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
          venv = pythonSets.${system}.mkVirtualEnv "semantic-bts-env" workspace.deps.default;
          piBundle = piBundles.${system};
          piLauncher = makePiLauncher {
            inherit pkgs;
            inherit venv;
            inherit piBundle;
          };
          tuiLauncher = makeTuiLauncher {
            inherit pkgs;
            inherit venv;
          };
        in
        {
          default = {
            type = "app";
            program = "${venv}/bin/semantic-bts";
          };
          # nix run .#pi  (or nix run github:xorq-labs/semantic-bts#pi)
          pi = {
            type = "app";
            program = "${piLauncher}/bin/semantic-bts-pi";
          };
          # nix run .#tui (or nix run github:xorq-labs/semantic-bts#tui)
          tui = {
            type = "app";
            program = "${tuiLauncher}/bin/semantic-bts-tui";
          };
        }
      );
    };
}
