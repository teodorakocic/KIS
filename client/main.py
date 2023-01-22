from array import array
import csv
from datetime import datetime
import os
from time import sleep
import psycopg2
from dotenv import load_dotenv
import paho.mqtt.client as mqtt
import random
from scipy.spatial.distance import cdist


def scipy_cdist(x, y):
    return cdist(x, y, metric='euclidean')      # Fastes way to calculate distance between two points


location = list()
name = list()
topics = list()
capacity = list()
occupancy = list()
gps_location = list()
municipality = set()
parking_region = dict()
clients = dict()
record = dict()


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


def define_regions_of_parkings():
    with open('client\\user_gps.csv', 'r') as file:
        csv_reader = csv.DictReader(file)
        for row in csv_reader:
            municipality.add(row['Municipality'])
    for id in range(len(location)):
        parking_region[id] = random.choice(list(municipality))


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

        connection.autocommit = True 
        postgre_fetch_parkings = 'SELECT osm_id AS parkingID, name AS parking, ST_X(ST_Transform(ST_Centroid(way), 4326)) as longitude, ST_Y(ST_Transform(ST_Centroid(way), 4326)) as latitude FROM public.planet_osm_polygon_mv WHERE ST_X(ST_Transform(ST_Centroid(way), 4326)) BETWEEN -74.0 AND -73.0 AND ST_Y(ST_Transform(ST_Centroid(way), 4326)) BETWEEN 42.0 AND 44.0'
        cursor = connection.cursor()
        cursor.execute('SELECT %s as connected;', ('Connection to postgres successful!',))
        print(cursor.fetchone())
        cursor.execute(postgre_fetch_parkings)
        record = cursor.fetchall()

        for row in record: 
            tmpLocation = array('f', [float(row[2]), float(row[3])])
            location.append([tmpLocation])
            if row[1] != None:
                tmpName = 'parking ' + row[1]
            else:
                tmpName = 'parking_' + str(row[0])
            name.append(tmpName)

    except (Exception, psycopg2.Error) as error:
        print('Error while fetching data from PostgreSQL', error)

    finally:
        # closing database connection.
        if connection:
            cursor.close()
            connection.close()
            print('PostgreSQL connection is closed')


def on_connect(client, obj, flags, rc):
    if rc == 0:
        print('Connected OK with result code ' + str(rc) + '\n')
    else:
        print('Bad connection returned code = ', rc)


def on_message(client, obj, message):
    print('Received message on topic ' + message.topic + ': ' + str(message.payload.decode('utf-8')) + '\n')


def on_subscribe(client, userdata, mid, granted_qos):
    print('Subscribed: ' + str(mid) + ' ' + str(granted_qos) + '\n')


def on_unsubscribe(client, userdata, mid):
    print('Unsubscribed: ' + str(mid) + '\n')   


def expiring_parking():
    
    for client in clients.keys():
        id = client[-8:]
        currentTime = datetime.now().strftime('%H:%M:%S')
        t1 = datetime.strptime(id, '%H:%M:%S')
        t2 = datetime.strptime(currentTime, '%H:%M:%S')
        dT = t2 - t1
        if dT.seconds > 60:
            clients[client].unsubscribe(record[clients[client]])


def generate_gps_coordinates():

    parking_spaces_occupied()
    define_regions_of_parkings()

    broker_address = os.environ.get('BROKER_ADDRESS')
    broker_port = int(os.environ.get('BROKER_PORT'))

    create_topics()
    
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
                print('Parking: ' + name[index] + ' with free spaces = ' + str(free_space))
                topic = 'parking/' + parking_region[index]
                print(index, topic)

                print('connecting ' + topic)
                tmpClientName = datetime.now().strftime('%H:%M:%S')
                client = mqtt.Client('client_' + tmpClientName) 
                clients[tmpClientName] = client
                client.on_connect = on_connect
                client.on_subscribe = on_subscribe
                client.on_message = on_message
                client.on_unsubscribe = on_unsubscribe

                print('Connecting to broker ...')
                client.connect(broker_address, broker_port) 
                print('...done')

                client.loop_start()
                client.subscribe(topic)
                record[client] = topic

                if free_space <= 0:
                    payload = 'New vehicle in the area ' + parking_region[index] + '. The vehicle entered parking ' + name[index] + ' with coordinates: { latitude: ' + str(location[index][0][0]) + '\t longitude: ' + str(location[index][0][1]) + ' }. No more free parking spaces left within this parking area!'
                else:
                    payload = 'New vehicle in the area ' + parking_region[index] + '. The vehicle entered parking ' + name[index] + ' with coordinates: { latitude: ' + str(location[index][0][0]) + '\t longitude: ' + str(location[index][0][1]) + ' }. Number of free parking spaces in this parking area is now ' + str(free_space) + '!'

                client.publish(topic, payload)

                expiring_parking()

                print('----------------------------------------------new vehicle approaching----------------------------------------------------\n')
            
            sleep(random.randint(1,5))


if __name__ == '__main__':

    postgis_connection_and_queries()
    generate_gps_coordinates()

