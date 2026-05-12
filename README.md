# try it out without install

#### run a directory's `__main__.py`
```
url=git+ssh://git@github.com/xorq-labs/semantic-bts-demo
uv tool run --isolated \
    --with $url \
    -- python -m semantic_bts_demo
```

#### run a module's `if __name__ == "__main__"` section
```
url=git+ssh://git@github.com/xorq-labs/semantic-bts-demo
uv tool run --isolated \
    --with $url \
    -- python -m semantic_bts_demo.hello
```

> [!NOTE]
> To target a private repo with `uv tool run`, use `ssh://git@` instead of `https://`

> [!NOTE]
> To target a branch with `uv tool run`, append `@$branchname` to the url

#### run a script from a packages's `[project.scripts]` without creating a venv
```
url=git+ssh://git@github.com/xorq-labs/semantic-bts-demo
nix develop --refresh \
    $url \
    --command semantic-bts-demo
```

> [!NOTE]
> To target a branch with `nix develop` or `nix run`, append `?ref=$branchname` to the url

#### drop into an ipython terminal with uv
```
url=git+ssh://git@github.com/xorq-labs/semantic-bts-demo
uv tool run --isolated \
    --with $url \
    ipython
```

#### drop into a bash shell with nix
```
url=git+ssh://git@github.com/xorq-labs/semantic-bts-demo
nix develop --refresh \
    $url
```

> [!NOTE]
> To target a private repo with `nix develop` or `nix run`, use `ssh://git@` instead of `https://`
