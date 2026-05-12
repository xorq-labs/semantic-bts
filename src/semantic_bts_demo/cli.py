import click


class DefaultCommandGroup(click.Group):
    def parse_args(self, ctx, args):
        if not args or (args[0] not in self.commands and not args[0].startswith("-")):
            args = ["hello", *args]
        return super().parse_args(ctx, args)


@click.group(cls=DefaultCommandGroup)
def cli() -> None:
    pass


@cli.command()
@click.argument("name", default="world", required=False)
def hello(name: str) -> None:
    click.echo(f"Hello, {name}!")
