from array import array
import csv
import os
from time import sleep
import psycopg2
import numpy as np
from dotenv import load_dotenv
import paho.mqtt.client as mqtt
import random
from scipy.spatial.distance import cdist

location = list()
topics = list()
capacity = list()
occupancy = list()
gps_location = list()
municipality = set()
parking_region = dict()

def postgis_connection_and_queries():

    load_dotenv()
    try:
    # Create connection to postgres
        connection = psycopg2.connect(host=os.environ.get('PG_HOST'),
                                    port=os.environ.get('PG_PORT'),
                                    user=os.environ.get('PG_USER'),
                                    password=os.environ.get('PG_PASSWORD'),
                                    dbname=os.environ.get('PG_DATABASE')
                                    )

        connection.autocommit = True  # Ensure data is added to the database immediately after write commands
        postgre_fetch_parkings = 'SELECT osm_id AS parkingID, name AS parking, ST_X(ST_Transform(ST_Centroid(way), 4326)) as longitude, ST_Y(ST_Transform(ST_Centroid(way), 4326)) as latitude FROM public.planet_osm_polygon_mv WHERE ST_X(ST_Transform(ST_Centroid(way), 4326)) BETWEEN -74.0 AND -73.0 AND ST_Y(ST_Transform(ST_Centroid(way), 4326)) BETWEEN 42.0 AND 44.0'
        cursor = connection.cursor()
        cursor.execute('SELECT %s as connected;', ('Connection to postgres successful!',))
        print(cursor.fetchone())
        cursor.execute(postgre_fetch_parkings)
        record = cursor.fetchall()

        for row in record: 
            tmpLocation = array('f', [float(row[2]), float(row[3])])
            location.append([tmpLocation])

    except (Exception, psycopg2.Error) as error:
        print("Error while fetching data from PostgreSQL", error)

    finally:
        # closing database connection.
        if connection:
            cursor.close()
            connection.close()
            print("PostgreSQL connection is closed")


def define_regions_of_parkings():
    with open('client\\user_gps.csv', 'r') as file:
        csv_reader = csv.DictReader(file)
        for row in csv_reader:
            municipality.add(row['Municipality'])
    for id in range(len(location)):
        parking_region[id] = random.choice(list(municipality))


def create_topics():
    for index in range(len(municipality)):
        topic = 'parking/' + str(list(municipality)[index])
        topics.append(topic)


def parking_spaces_occupied():
    with open('client\\parking_capacity.csv', 'r') as file:
        csv_reader = csv.DictReader(file)
        for row in csv_reader:
            capacity.append(int(row['Capacity']))
            occupancy.append(int(row['Occupancy']))


def scipy_cdist(x, y):
    return cdist(x, y, metric='euclidean')


def on_connect(client, obj, flags, rc):
    if rc == 0:
        print("Connected OK with result code " + str(rc))
    else:
        print("Bad connection returned code = ", rc)


def on_message(client, obj, message):
    print('Received message on topic ' + message.topic + ": " + str(message.payload.decode("utf-8")))


def generate_gps_coordinates():
    broker_address = os.environ.get('BROKER_ADDRESS')
    broker_port = int(os.environ.get('BROKER_PORT'))
    with open('client\\user_gps.csv', 'r') as file:
        csv_reader = csv.DictReader(file)
        for row in csv_reader:
            if row['Latitude'] != '' and row['Longitude'] != '':
                tmpGpsLocation = array('f', [float(row['Longitude']), float(row['Latitude'])])
                gps_location.append([tmpGpsLocation])

                min_dist = list()
                for position in location:
                    tmp_distance = scipy_cdist(position, [tmpGpsLocation])
                    min_dist.append(tmp_distance)

                index = min_dist.index(min(min_dist))
                occupancy[index] += 1
                free_space = capacity[index] - occupancy[index]
                topic = 'parking/' + parking_region[index]
                print(index, topic)

                print('connecting ' + topic)
                print("Creating new instance ...")
                client = mqtt.Client() 
                client.on_connect = on_connect
                client.on_message = on_message

                print("Connecting to broker ...")
                client.connect(broker_address, broker_port) 
                print("...done")

                client.subscribe(topic)

                if free_space <= 0:
                    payload = 'New vehicle in the area ' + parking_region[index] + '. The vehicle entered parking whose coordinates are: { latitude: ' + str(location[index][0][0]) + '\t longitude: ' + str(location[index][0][1]) + ' }. No more free parking spaces left within this parking area!'
                else:
                    payload = 'New vehicle in the area ' + parking_region[index] + '. The vehicle entered parking whose coordinates are : { latitude: ' + str(location[index][0][0]) + '\t longitude: ' + str(location[index][0][1]) + ' }. Number of free parking spaces in this parking area is now ' + str(free_space) + '!'

                client.publish(topic, payload)
                client.loop_start()

            sleep(2)


postgis_connection_and_queries()
parking_spaces_occupied()
define_regions_of_parkings()
create_topics()
generate_gps_coordinates()

