from pathlib import Path
import sys


root = Path(sys.argv[1])

udp = root / "lib/isc/netmgr/udp.c"
content = udp.read_text()
content = content.replace("\tUNUSED(extrahandlesize);\n", "", 1)
udp.write_text(content)

interface_manager = root / "lib/ns/interfacemgr.c"
content = interface_manager.read_text()
marker = "#define LISTENING(ifp)"
compatibility = """#if defined(__wasi__) && !defined(MSGHDR)
struct edgeterm_route_message {
	unsigned int message_type;
};
#define MSGHDR edgeterm_route_message
#define MSGTYPE message_type
#define RTM_NEWADDR 1
#define RTM_DELADDR 2
#endif

"""
if compatibility not in content:
    if marker not in content:
        raise RuntimeError("BIND interface manager marker was not found")
    content = content.replace(marker, compatibility + marker, 1)
interface_manager.write_text(content)
