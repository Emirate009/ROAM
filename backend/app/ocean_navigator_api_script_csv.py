import time
import requests
import os
from urllib.parse import urlencode
import json
import pandas as pd
from datetime import datetime, timezone, timedelta

EPOCH_1950 = datetime(1950, 1, 1, tzinfo=timezone.utc)

def timestamp_to_datetime(timestamp):
    return EPOCH_1950 + timedelta(seconds=int(timestamp))

def requestFile(timestamp, station=[49.5, -127.23333299999999], output_dir=None):
   # json object for the query
   query = {
      "dataset":"giops_day",
      "names":[None],
      "station":[station],
      "showmap":0,
      "time":timestamp
   }


   # Assemble full request
   base_url = "https://www.oceannavigator.ca/api/v2.0/plot/sound?"
   url = base_url + urlencode({"query": json.dumps(query)}) + '&save=True&format=csv&size=10x7&dpi=144'
   print(url)



   print(f"Requesting timestamp: {timestamp}")
   print(f"Converted date: {timestamp_to_datetime(timestamp)}")
   print(f"URL: {url}")

   try:
      data_file = requests.get(url, stream=True, timeout=30)
   except requests.exceptions.RequestException as error:
      raise RuntimeError(
         f"Could not connect to Ocean Navigator: {error}"
      ) from error

   print(f"HTTP status: {data_file.status_code}")
   print(f"Content-Type: {data_file.headers.get('Content-Type')}")
   print(f"Response size: {len(data_file.content)} bytes")

   # Print the server data_file when it is not successful.
   if not data_file.ok:
      preview = data_file.text[:1000]
      raise RuntimeError(
         f"Ocean Navigator returned HTTP {data_file.status_code}.\n"
         f"Response preview:\n{preview}"
      )

   response_text = data_file.text

   known_errors = [
      "NetCDF file list is empty",
      "RuntimeError",
      "Traceback",
      "Internal Server Error",
   ]

   for error_text in known_errors:
      if error_text.lower() in response_text.lower():
         raise RuntimeError(
               f"Ocean Navigator returned an error instead of CSV data:\n"
               f"{response_text[:1500]}"
         )

   # Successful Ocean Navigator CSV files should contain these metadata lines.
   if "Timestamp:" not in response_text:
      raise RuntimeError(
         "The data_file did not contain a Timestamp header and may not "
         f"be a valid Ocean Navigator CSV.\n\n"
         f"Response preview:\n{response_text[:1500]}"
      )

   output_directory = output_dir or os.path.join("ssp", "ctd")
   os.makedirs(output_directory, exist_ok=True)

   fname = os.path.join(output_directory, f"{timestamp}.csv")

   with open(fname, "wb") as file:
      file.write(data_file.content)

   print(f"Saved file: {fname}")
   return fname


   # # Save file and finish
   # data_file = requests.get(url, stream=True)

   # # change this if you want a different save location
   # location = os.getcwd()
   # fname = str("ssp/ctd/") + str(query["time"]) + ".csv"
   # with open(fname, "wb") as location:
   #    print('Saving File')
   #    location.write(data_file.content)
   #    print('Done')

   #    df = pd.read_csv(fname)
   #    if "RuntimeError: NetCDF file list is empty." in df:
   #             print("RuntimeError: NetCDF file list is empty.")

   # return fname

def formatFileName(fname, output_dir=None):
   df = pd.read_csv(fname, nrows=2, header=None)  # Read only the first line after skipping 2 rows

   timestamp_line = str(df.iloc[1, 0])

   # Example: "Timestamp: 2026-06-06 12:00:00+00:00"
   timestamp = timestamp_line.split("Timestamp:")[1].strip()

   # Convert the timestamp to the desired format
   dt = datetime.fromisoformat(timestamp)
   formatted = dt.strftime("%Y%m%d%H%M")

   # Rename the file
   output_directory = output_dir or os.path.join("ssp", "ctd")
   new_fname = os.path.join(output_directory, f"{formatted}.csv")
   os.rename(fname, new_fname)

   return new_fname

def formatFile(fname):
   print(fname)
   df = pd.read_csv(fname, skiprows=2)

   # Remove the first two columns
   df = df.iloc[2:, 2:]

   df.to_csv(fname, index=False)

def generateTimestamps(time):

   # Generate timestamps at 2 week intervals until back to 1950
   timestamps = []
   while time > 0:
      timestamps.append(time)
      time -= 1209600
   return timestamps

def seconds_since_1950_at_midnight(dt):
    epoch_1950 = datetime(1950, 1, 1, tzinfo=timezone.utc)

    dt = dt.astimezone(timezone.utc).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )

    return int((dt - epoch_1950).total_seconds())

def getSSP(coordinates, output_dir=None):

   #Seconds until 1950-01-01T00:00:00Z
   requested_date = datetime.now(timezone.utc)
   timestamp = seconds_since_1950_at_midnight(requested_date)

   fname = requestFile(timestamp, coordinates, output_dir)
   fname = formatFileName(fname, output_dir)
   formatFile(fname)

   return fname

   # timestamps = generateTimestamps(seconds_since_1950)
   # for timestamp in timestamps:
   #    try: 
   #       fname = requestFile(timestamp)
   #       print(fname)
   #       fname = formatFileName(fname)
   #       print(fname)
   #       formatFile(fname)
   #    except Exception as e:
   #       print(f"Error occurred while processing time {timestamp}: {e}")