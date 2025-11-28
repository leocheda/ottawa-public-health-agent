from time import sleep
from bs4 import BeautifulSoup
from contextlib import suppress
from patchright.sync_api import sync_playwright
from pprint import pp
import bs4


global debug
debug = False

global dcl_event_count
dcl_event_count = 0

def inc_dcl_event_count():
    global dcl_event_count
    dcl_event_count = dcl_event_count + 1
    print(f"DCL Event Count: {dcl_event_count}", flush=True) if debug else None
    return None

global didFrameNavigate
didFrameNavigate = False


def frame_navigated_handler(frame):
    global didFrameNavigate
    print(f"Frame navigated to {frame.url}", flush=True) if debug else None
    didFrameNavigate = True
    return None


def retrieve_dom_for_outbreaks_report():
    # Outbreaks
    url = 'https://app.powerbi.com/view?r=eyJrIjoiMzIxNGU5ODMtNmRjZi00OWNmLWIwYWUtMmY0MzA2NzZmZjYyIiwidCI6ImRmY2MwMzNkLWRmODctNGM2ZS1hMWI4LThlYWE3M2YxYjcyZSJ9&pageName=ReportSection7971162d78b00a048576'

    html = ""
    p = sync_playwright().start()
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page()
    page.on("framenavigated", frame_navigated_handler)
    page.on("domcontentloaded", inc_dcl_event_count)
    page.goto(url, wait_until="domcontentloaded")
    print("Page.goto returned", flush=True) if debug else None

    while not didFrameNavigate:
        sleep(1)

    sleep(5)
    html = page.content()
    with open("last-retrieval-outbreaks.html", "w", encoding="utf-8") as f:
        f.write(html)
    browser.close()
    return html


def retrieve_dom_for_diseases_of_ph_significance():
    url = 'https://app.powerbi.com/view?r=eyJrIjoiODVkZmU3NzItNTliYi00YzFlLTk2ZWItODcwOWU5NDhlMGU3IiwidCI6ImRmY2MwMzNkLWRmODctNGM2ZS1hMWI4LThlYWE3M2YxYjcyZSJ9&pageName=ReportSection1b2070dda67567cb9a79'
    html = ""
    p = sync_playwright().start()
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page()
    page.on("framenavigated", frame_navigated_handler)
    page.on("domcontentloaded", inc_dcl_event_count)
    page.goto(url, wait_until="domcontentloaded")
    print("Page.goto returned", flush=True) if debug else None

    while not didFrameNavigate:
        sleep(1)
    sleep(2)

    dataTablesButtonList = page.query_selector_all('div.pageNavigator[role="button"]')
    dataTablesButton = dataTablesButtonList[2]
    sleep(4)
    
    dataTablesButton.evaluate("element => element.setAttribute('visible', 'true')")
    dataTablesButton.click(force=True)
    sleep(5)
    html = page.content()
    with open("last-retrieval-diseases-of-ph-significance.html", "w", encoding="utf-8") as f:
        f.write(html)
    browser.close()
    return html


def extract_table_data_from_powerbi_html(html: str):
    REMOVE_ATTRIBUTES = ['style', 'class', 'aria', 'tabindex', 'aria-colindex']
    attributes = bs4.builder.HTMLTreeBuilder.DEFAULT_CDATA_LIST_ATTRIBUTES

    soup = BeautifulSoup(html, 'html5lib', multi_valued_attributes=attributes)
    for tag in soup.descendants:
        if isinstance(tag, bs4.element.Tag):
            tag.attrs = {key: value for key, value in tag.attrs.items()
                        if key not in REMOVE_ATTRIBUTES}
    pres = soup.find_all(role=["columnheader", "rowheader", "gridcell"])
    column_headers = list()
    current_row = list()
    current_table = list()
    datasets = list()

    for pres_item in pres:
        if 'columnheader' in pres_item.attrs['role']:
            # This is a new table
            if current_row != []:
                # We need to add the last row to the current table
                current_table.append(current_row)
                print(current_row) if debug else None

                # Reset for new row
                current_row = []

            if column_headers == [] and current_table != []:
                # Record the just ended table
                datasets.append(current_table)

                # Reset table
                current_table = list()

                # Starting the new table
                print("---- New Table ----") if debug else None

            # Add the column headers
            column_headers.append(pres_item.get_text(strip=True))

        # We treat this as a cell in the current row
        # Not all tables use rowheaders
        if 'rowheader' in pres_item.attrs['role']:
            # This is a new row
            if current_row != []:
                # We need to add the last row to the current table
                current_table.append(current_row)
                print(current_row) if debug else None
                current_row = []

            if column_headers != []:
                print(column_headers) if debug else None
                current_table.append(column_headers)

                # Reset column headers already recorded
                column_headers = []

            # Add the row header as the first item in the current row
            current_row.append(pres_item.get_text(strip=True))

        if 'gridcell' in pres_item.attrs['role']:
            if column_headers != []:
                current_table.append(column_headers)
                print(column_headers) if debug else None
                column_headers = []

            if len(current_row) > 1 and pres_item.attrs['column-index'] == '0':
                # This is a cell in the new row, we need to record the current row first
                # - If len(current_row) is 0 or 1, we are still building the row
                # - When len(current_row) = 1 and column-index = 0, we have just seen a rowheader
                # - When len(current_row) > 1 and column-index = 0, we know we are starting a new row
                current_table.append(current_row)
                print(current_row) if debug else None
                current_row = []


            # Record the cell value
            current_row.append(pres_item.get_text(strip=True))

    # We're done all the items, and need to record the last row if any
    if current_row != []:
        current_table.append(current_row)
        datasets.append(current_table)
        print(current_row) if debug else None

    return datasets


def main():
    html = retrieve_dom_for_outbreaks_report()
    datasets = extract_table_data_from_powerbi_html(html)
    print()
    pp(datasets)


if __name__ == "__main__":
    main()
