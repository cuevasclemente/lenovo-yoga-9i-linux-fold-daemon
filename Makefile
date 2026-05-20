PREFIX ?= /usr/local
BINDIR ?= $(PREFIX)/bin
SYSTEMD_DIR ?= /etc/systemd/system
SERVICE ?= yoga-fold-daemon.service
BIN ?= yoga-fold-daemon
PYTHON ?= python3

.PHONY: all check install uninstall enable disable restart status logs install-modprobe-blacklist remove-modprobe-blacklist

all: check

check:
	$(PYTHON) -m py_compile yoga-fold-daemon.py

install: check
	install -Dm0755 yoga-fold-daemon.py $(DESTDIR)$(BINDIR)/$(BIN)
	install -Dm0644 yoga-fold-daemon.service $(DESTDIR)$(SYSTEMD_DIR)/$(SERVICE)
	@if command -v systemctl >/dev/null 2>&1; then systemctl daemon-reload; fi
	@echo "Installed $(BIN) and $(SERVICE). Run 'sudo make enable' to start at boot."

uninstall: disable
	rm -f $(DESTDIR)$(BINDIR)/$(BIN)
	rm -f $(DESTDIR)$(SYSTEMD_DIR)/$(SERVICE)
	@if command -v systemctl >/dev/null 2>&1; then systemctl daemon-reload; fi

enable:
	systemctl enable --now $(SERVICE)

disable:
	-systemctl disable --now $(SERVICE)

restart:
	systemctl restart $(SERVICE)

status:
	systemctl --no-pager --full status $(SERVICE)

logs:
	journalctl -u $(SERVICE) -n 80 --no-pager

install-modprobe-blacklist:
	install -Dm0644 /dev/null /etc/modprobe.d/blacklist-lenovo-ymc.conf
	printf '%s\n' 'blacklist lenovo_ymc' 'install lenovo_ymc /bin/false' > /etc/modprobe.d/blacklist-lenovo-ymc.conf
	@echo "Installed /etc/modprobe.d/blacklist-lenovo-ymc.conf. Kernel-command-line blacklist is still recommended for initramfs/early boot."

remove-modprobe-blacklist:
	rm -f /etc/modprobe.d/blacklist-lenovo-ymc.conf
