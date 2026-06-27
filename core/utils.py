def fmt_size(b):
    b = max(0, int(b))
    if b < 1024:
        return f"{b} B"
    elif b < 1048576:
        return f"{b / 1024:.0f} KB"
    elif b < 1073741824:
        return f"{b / 1048576:.1f} MB"
    elif b < 1099511627776:
        return f"{b / 1073741824:.2f} GB"
    else:
        return f"{b / 1099511627776:.2f} TB"


def fmt_speed(b):
    b = max(0, b)
    if b < 1024:
        return f"{b:.0f} B/s"
    elif b < 1048576:
        return f"{b / 1024:.0f} KB/s"
    elif b < 1073741824:
        return f"{b / 1048576:.1f} MB/s"
    elif b < 1099511627776:
        return f"{b / 1073741824:.2f} GB/s"
    else:
        return f"{b / 1099511627776:.2f} TB/s"
