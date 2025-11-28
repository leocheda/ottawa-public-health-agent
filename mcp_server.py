from mcp.server.fastmcp import FastMCP
from tools.ottawa_health_scraper import retrieve_health_data_tool


def format_datasets_as_csv(datasets):
    """
    Convert the list of datasets into CSV-formatted text.
    Each dataset is a table (list of rows).
    """
    output = []
    for i, table in enumerate(datasets):
        output.append(f"\n=== Table {i + 1} ===\n")
        for row in table:
            # Join row items with commas, handling empty cells
            csv_row = ",".join(str(cell) if cell else "" for cell in row)
            output.append(csv_row)
        output.append("")  # Blank line between tables
    return "\n".join(output)


# Create an MCP server
mcp = FastMCP("Ottawa Health")


@mcp.tool()
async def get_ottawa_outbreaks() -> str:
    """
    Retrieves current Ottawa Public Health outbreak data.
    Returns CSV-formatted tables of active outbreaks in:
    - Camp, Congregate Care, Communal Living Facility
    - Correctional Facility, Group Home, Supportive Living
    - Hospice, Hospital, Licensed Child Care Facility/ Daycare
    - Long Term Care Home, Retirement Home, Rooming House
    - Elementary School, Secondary School, Post Secondary School
    - Shelter, Supported Independent Living
    """
    datasets = await retrieve_health_data_tool()
    return format_datasets_as_csv(datasets)


if __name__ == "__main__":
    mcp.run()
