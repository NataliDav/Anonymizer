import sys


def main():
    argv = sys.argv[1:]
    if argv and argv[0] in ("encode", "decode"):
        from anonymizer.cli import run_cli
        return run_cli(argv)
    from anonymizer.gui.app import App
    app = App()
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
