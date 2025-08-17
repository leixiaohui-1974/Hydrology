from whitebox.whitebox_tools import WhiteboxTools

wbt = WhiteboxTools()
tools = wbt.list_tools()
for tool_name in tools:
    if 'junction' in tool_name or 'stream' in tool_name:
        print(tool_name)
