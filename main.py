import os, traceback
from datetime import datetime
from pprint import pprint

import pandas as pd
import plotly.express as px
import plotly.io as pio
from notion_client import Client
from notion_client.helpers import iterate_paginated_api

from template import template_start, template_end
from config import config

token = config["token"]
database_id = config["database_id"]
output_graphic = config["output_graphic"]
output_table = config["output_table"]
bookposts = config["bookposts"]
DEBUG = True


def main():
    entries = pull_database()
    df = generate_dataframe(entries)

    def create_rel_links(tit):
        if tit in bookposts:
            return f"[{tit}](/posts/{bookposts[tit]})"
        return tit

    # Create plot and write to
    fig = plot(interpolate_pages_over_time(df, rolling=7))
    with open(output_graphic, "w") as f:
        pio.write_html(fig, f)

    df["Title"] = df.Title.apply(create_rel_links)
    df = df.drop(columns=["# Pages"])

    # Create new Markdown file
    with open(output_table, "w") as f:
        f.write(template_start + df.to_markdown(index=False) + template_end)
        print("Just overwrote " + output_table)


def pull_database():
    # authenticates a Notion client and returns the database
    notion = Client(auth=token)
    return list(iterate_paginated_api(notion.databases.query, database_id=database_id))


def parse_entry(dic):
    # takes a table row and returns a dictionary of the values I care about
    parsed_dict = {}
    dic = dic["properties"]
    try:
        if DEBUG:
            pprint(dic)
            print()
        if dic["Status"]["select"]["name"] != "Finished" or dic["Content Type"][
            "select"
        ]["name"] not in set(["Book", "Audiobook"]):
            return {}
        parsed_dict["Score"] = dic["Score /5"]["select"]["name"]
        parsed_dict["Start Date"] = dic["Dates"]["date"]["start"]
        parsed_dict["End Date"] = dic["Dates"]["date"]["end"]
        try:
            parsed_dict["# Pages"] = int(dic["Page Length"]["number"])
        except:
            parsed_dict["# Pages"] = dic["Page Length"]["number"]
        parsed_dict["Author"] = dic["Author"]["multi_select"][0]["name"]
        parsed_dict["Title"] = dic["Name"]["title"][0]["plain_text"]
    except Exception as e:
        # print(parsed_dict["Content Type"]["select"]["name"])
        print(e)
        traceback.print_exc()
        pprint(dic)

    return parsed_dict


def generate_dataframe(entries):
    # Creates a dataframe given a list of entries, or the return value of pull_database
    flat_list = []
    for e in entries:
        flat_list += e
    df = (
        pd.DataFrame.from_records([parse_entry(e) for e in flat_list])
        .dropna()
        .sort_values("End Date")
    )
    df["# Pages"] = df["# Pages"].astype(int)

    df = df[
        ["Title", "Author", "Start Date", "End Date", "Score", "# Pages"]
    ].sort_values("End Date", ascending=False)
    if DEBUG:
        print(df.to_markdown())
    return df


def interpolate_pages_over_time(df, rolling=None):
    """
    Takes a dataframe of books and returns a dataframe with average pages read per day.
    If given, rolling takes a number of days to compute a rolling average over.
    """

    page_dict = {
        date: (0, [])
        for date in pd.date_range(df["Start Date"].min(), df["End Date"].max())
    }

    def helper(x):
        dates = pd.date_range(x["Start Date"], x["End Date"])
        for date in dates:
            pgs, books = page_dict[date]
            pgs += float(x["# Pages"] / len(dates))
            books.append(f"{x.Title} - {x.Author}")
            page_dict[date] = pgs, books

    df.apply(helper, axis=1)
    new_df = pd.DataFrame.from_dict(
        page_dict, orient="index", columns=["# Pages", "Titles"]
    )
    new_df["# Pages"] = new_df["# Pages"].round()
    new_df["Date"] = new_df.index
    new_df["Titles"] = new_df.Titles.apply(lambda x: "<br>".join(x))

    if rolling:
        new_df["Rolling"] = (
            new_df["# Pages"].rolling(window=rolling, min_periods=1).mean().round()
        )

    return new_df


def plot(df):
    # Creates a plotly plot
    # EX: plot(interpolate_pages_over_time(df, rolling=7))

    fig = px.line(
        df,
        x="Date",
        y="Rolling",
        title="My Reading Over Time",
        hover_name="Titles",
        template="seaborn",
    )

    fig.update_xaxes(rangeslider_visible=True)
    fig.update_xaxes(
        rangeslider_visible=True,
        rangeselector=dict(
            buttons=list(
                [
                    dict(count=1, label="1m", step="month", stepmode="backward"),
                    dict(count=6, label="6m", step="month", stepmode="backward"),
                    dict(count=1, label="YTD", step="year", stepmode="todate"),
                    dict(count=1, label="1y", step="year", stepmode="backward"),
                    dict(step="all"),
                ]
            )
        ),
    )

    texts = [
        (datetime(2022, 5, 1), "Slovak Shield"),
        (datetime(2021, 5, 1), "Master's Thesis"),
        (datetime(2020, 3, 10), "Coronavirus"),
        (datetime(2019, 7, 23), "Boston Move"),
        (datetime(2018, 7, 13), "Poland"),
    ]
    for date, label in texts:
        fig.add_annotation(
            dict(
                x=date,
                y=df.loc[date].Rolling.round(),
                xref="x",
                yref="y",
                text=label,
                font_size=15,
                borderwidth=5,
                showarrow=True,
                arrowhead=7,
                arrowsize=1,
                arrowwidth=2,
                ax=0,
                ay=30,
            )
        )
    fig.update_layout(yaxis_title="Average Pages per Day (rolling)")
    fig.show()
    return fig


if __name__ == "__main__":
    main()
