import argparse
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


# function to convert time from string to seconds
def time_to_seconds(time):
    time_split = time.split(":")
    seconds = float(time_split[-1])
    if len(time_split) > 1:
        seconds += float(time_split[-2]) * 60
    if len(time_split) > 2:
        seconds += float(time_split[-3]) * 3600
    return seconds


def main():
    # get arguments of real data column, simulation data column, real data path and simulation data path
    parser = argparse.ArgumentParser()
    parser.add_argument("--real_col", type=str, default="RPM")
    parser.add_argument("--sim_col", type=str, default="RPM")
    parser.add_argument("--start_time", type=str, default="0")
    parser.add_argument("--end_time", type=str, default="1:00")
    parser.add_argument("--real_path", type=str, default="data/real_data.csv")
    parser.add_argument(
        "--sim_path", type=str, default="../frontend/simulation_output.csv"
    )
    args = parser.parse_args()

    # read real data and simulation data
    real_data = pd.read_csv(args.real_path)
    sim_data = pd.read_csv(args.sim_path)

    # parse start and end time from string to seconds
    start_time = time_to_seconds(args.start_time)
    end_time = time_to_seconds(args.end_time)

    # strip whitespace from column names
    real_data.columns = real_data.columns.str.strip()
    sim_data.columns = sim_data.columns.str.strip()

    # start real data at the fist timestamp if start time is too small
    start_real_time = np.max([start_time, real_data["Timestamp (ms)"].iloc[0] / 1000])

    # filter real data to match start and end time
    real_data = real_data[
        (real_data["Timestamp (ms)"] >= start_real_time * 1000)
        & (real_data["Timestamp (ms)"] <= end_time * 1000)
    ]

    # convert real data timestamps to seconds and adjust by start time
    real_data["time"] = real_data["Timestamp (ms)"] / 1000 - start_time

    # calculate end real_data time
    end_real_time = real_data["time"].iloc[-1]

    # cut off simulation data to match real data
    sim_data = sim_data[(sim_data["time"] <= end_real_time)]

    # interpolate the specific column of simulation data to match the real data timestamps
    interpolated_data = np.interp(
        real_data["time"], sim_data["time"], sim_data[args.sim_col]
    )

    # calculate squared error between real data and interpolated simulation data
    squared_error = (real_data[args.real_col] - interpolated_data) ** 2

    # plot real data, simulation data and the mean squared error all in one graph
    # data share the left y-axis, mse uses the right y-axis
    fig, ax1 = plt.subplots()
    ax2 = ax1.twinx()

    ax1.plot(
        real_data["time"],
        real_data[args.real_col],
        label=f"{args.real_col} ({args.real_path.split('/')[-1]})",
        color="blue",
    )
    ax1.plot(
        real_data["time"],
        interpolated_data,
        label=f"{args.sim_col} ({args.sim_path.split('/')[-1]})",
        color="green",
    )
    ax2.plot(real_data["time"], squared_error, label="Squared Error", color="red")
    ax1.set_xlabel("Time (s)")
    ax1.set_ylabel(f"{args.real_col} & {args.sim_col}")
    ax2.set_ylabel("Mean Squared Error")

    # get each set of legends
    lines, labels = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()

    # add mse to squared error in parenthesis
    labels2 = [f"{label} (MSE: {np.mean(squared_error):.2f})" for label in labels2]

    # combine legends
    fig.legend(lines + lines2, labels + labels2, loc="upper left")

    plt.show()


if __name__ == "__main__":
    main()
