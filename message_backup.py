# -*- coding: utf-8 -*-
from __future__ import print_function
import sqlite3
import sys
import re
import datetime
import hashlib
import os
import glob
import shutil
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--destination", help="Specify the path where you want the messages backup files to be saved. If you don't specify a path, a directory will be created on the Desktop. (Example: `-d ~/Desktop/message_backup`)",
                    type=str)
    parser.add_argument("-b", "--backup", help="Specify the path to the backup you want to use. If you don't specify a path, the latest iTunes iOS backup will be used. (Example: `-b /Users/NAME/Library/Application\ Support/MobileSync/Backup/7b93de038108pz5w6b30mr9271938mcy928g93yu`)")
    args = parser.parse_args()

    # Get destination location from user or set to default as desktop with today's date
    destination_path = args.destination if args.destination is not None else os.path.expanduser('~/Desktop') + '/iOS_messages_archive_' + datetime.datetime.now().strftime("%Y-%m-%d")

    # If the destination directory doesn't already exist, create it!
    if not os.path.exists(destination_path):
        os.makedirs(destination_path)
    else:
        print('Error: Directory already exists. Please select a new location.')
        sys.exit()

    # lol. So many texts.
    print('Please wait... This may take a while...')

    # Get the path to the iOS backup file
    backup_path = args.backup if args.backup is not None else get_latest_iOS_backup_path()

    # Connect to the sms.db file from the latest iOS backup. (3d0d7e5fb2ce288813306e4d4636395e047a3d28 is the sha1 hashed name for the sms.db file)
    conn = sqlite3.connect(backup_path + '/3d/3d0d7e5fb2ce288813306e4d4636395e047a3d28')
    db_cursor = conn.cursor()

    # Get list of all unique phone numbers/iMessage accounts sent/received messages to/from
    unique_number_query = 'SELECT DISTINCT id FROM handle;'
    db_cursor.execute(unique_number_query)
    all_numbers = db_cursor.fetchall()
    num_of_numbers = len(all_numbers)

    # Get list of all unique group chats
    unique_roomnames_query = 'SELECT DISTINCT cache_roomnames FROM message;'
    db_cursor.execute(unique_roomnames_query)
    all_rooms = db_cursor.fetchall()
    num_of_rooms = len(all_rooms)

    # Initialize progress bar
    total_tasks = num_of_numbers + num_of_rooms
    status_index = 0
    printProgressBar(status_index, total_tasks, prefix = 'Progress:', suffix = 'Complete', length = 50)

    # First print an html document for each unique phone number
    status_index = create_single_conversation_documents(all_numbers, db_cursor, destination_path, backup_path, status_index, total_tasks)

    # Next, print an html document for each unique group chat
    create_group_conversation_documents(all_rooms, db_cursor, destination_path, backup_path, status_index, total_tasks)

    # Close sql connection
    conn.close()
    print('\nBackup Complete!\n')


# Creates an html document with every text message and attachment for each conversation with a single contact
## all_numbers: A list with each phone number (or apple id, etc.) the user had correspondence with
## db_cursor: SQL cursor for the backup database
## destination_path: The path specified where the files will be output to
## backup_path: the path to the iTunes iOS backup file specified to pull information from
## status_index: An integer index variable which keeps track of progress in the progess bar
## total_tasks: An integer holding the number of total conversation documents (including group chats). Considered '100%' for progress bar
### returns: The updated status_index so we can pass it along to the create_group method and have accurate status updates
def create_single_conversation_documents(all_numbers, db_cursor, destination_path, backup_path, status_index, total_tasks):
    for number in enumerate(all_numbers):
        # Ensure the phone number is ascii compatible
        number = number[1][0].encode('ascii')

        # Get list of all messages for specified phone number from SQL db
        sql_query = 'SELECT * FROM (SELECT * FROM (SELECT mess_hand_chat_join.mess_ROWID as message_id, mess_hand_chat_join.id as id, mess_hand_chat_join.text as text, mess_hand_chat_join.service as service, mess_hand_chat_join.is_from_me as is_from_me, mess_hand_chat_join.date as \'date\', mess_hand_chat_join.date_read as date_read, mess_hand_chat_join.date_delivered as date_delivered, chat.ROWID as chat_id, chat.room_name as room_name FROM (SELECT * FROM (SELECT message.ROWID as mess_ROWID, handle.id as id, message.text as text, message.service as service, message.is_from_me as is_from_me, message.date as \'date\',  message.date_read as date_read, message.date_delivered as date_delivered FROM handle INNER JOIN message ON message.handle_id = handle.ROWID) as message_info INNER JOIN chat_message_join on message_info.mess_ROWID = chat_message_join.message_id) as mess_hand_chat_join INNER JOIN chat on mess_hand_chat_join.chat_id = chat.ROWID) as message_chat_info LEFT JOIN message_attachment_join on message_chat_info.message_id = message_attachment_join.message_id) as message_chat_att_join LEFT JOIN attachment on message_chat_att_join.attachment_id = attachment.ROWID WHERE id = \'' + number + '\' ORDER BY message_chat_att_join.date ASC;'
        db_cursor.execute(sql_query)
        all_rows = db_cursor.fetchall()

        # Create new html file
        new_html_filename = destination_path + '/' + number + '.html'
        new_file = open(new_html_filename, "w")
        lines_written = 0

        # Write out html header with CSS styling
        write_html_header(new_file)

        new_file.write('<h1>Conversations with ' + number + '</h1>')

        # Write table header row
        new_file.write('<table>')

        # For each message create a row in the table with the message information
        for row in all_rows:
            # SQL Response column order -> [0,message_id][1,id][2,text][3,service][4,is_from_me][5,date][6,date_read][7,date_delivered][8,chat_id][9,room_name][10,message_id:1][11,attachment_id][12,ROWID][13,guid][14,created_date][15,start_date][16,filename][17,uti][18,mime_type][19,transfer_state][20,is_outgoing][21,user_info][22,transfer_name][23,total_bytes][24,is_sticker][25,sticker_user_info][26,attribution_info][27,hide_attachment][28,ck_sync_state][29,ck_server_change_token_blob][30,ck_record_id][31,original_guid]
            phone_num = row[1]
            message = row[2]
            service = row[3]
            is_from_me = row[4]
            date_timestamp = row[5]
            room_name = row[9]
            attachment_filename = row[16]
            mime_type = row[18]

            # If the message is from a group chat, don't add it now, we'll record that in a separate file
            if room_name is None:
                lines_written += 1
                # Print out the message as a row in the table
                add_row_to_table(new_file, backup_path, destination_path, phone_num, message, service, is_from_me, date_timestamp, attachment_filename, mime_type)

        # End html file
        new_file.write('</body></html>')

        # If no lines written in the file (due to no messages sent/recieved with that phone number), just delete the created file
        if lines_written < 1:
            os.remove(new_html_filename)

        # Update Progress Bar
        status_index += 1
        printProgressBar(status_index, total_tasks, prefix = 'Progress:', suffix = 'Complete', length = 50)
    return status_index

# Creates an html document with every text message and attachment for each group chat
## all_rooms: A list with each group chat the user was a part of
## db_cursor: SQL cursor for the backup database
## destination_path: The path specified where the files will be output to
## backup_path: the path to the iTunes iOS backup file specified to pull information from
## status_index: An integer index variable which keeps track of progress in the progess bar
## total_tasks: An integer holding the number of total conversation documents (including group chats). Considered '100%' for progress bar
### returns: nothing
def create_group_conversation_documents(all_rooms, db_cursor, destination_path, backup_path, status_index, total_tasks):
    for room in enumerate(all_rooms):
        cache_roomname = room[1][0]
        if cache_roomname is not None:
            # Get most-recent 'title' of groupchat. Users can change the name of the groupchat (or not set one at all...) Get the latest set name
            group_name_query = 'SELECT group_title, max(date) FROM message WHERE cache_roomnames = \'' + cache_roomname + '\' AND group_title IS NOT NULL;'
            db_cursor.execute(group_name_query)
            room_name = db_cursor.fetchone()
            # Ensure the name is in ascii
            if room_name[0] is not None:
                room_name = room_name[0].encode('ascii')
            else:
                # If the users never set a name for the group chat, just call it untitled
                room_name = 'untitled'

            # Create new html file and call it the name of the group chat + the cached roomname from the backup (to avoid name collisions)
            new_html_filename = destination_path + '/' + room_name + '_' + cache_roomname + '.html'
            new_file = open(new_html_filename, "w")
            lines_written = 0

            # Write out html header with CSS styling
            write_html_header(new_file)

            new_file.write('<h1>' + room_name + ' Group Chat</h1>')

            # Write table header row
            new_file.write('<table>')

            # Get list of all messages sent or received in the group chat
            group_messages_query = 'SELECT * FROM (SELECT * FROM (SELECT mess_hand_chat_join.mess_ROWID as message_id, mess_hand_chat_join.id as id, mess_hand_chat_join.text as text, mess_hand_chat_join.service as service, mess_hand_chat_join.cache_roomnames as cache_roomnames, mess_hand_chat_join.is_from_me as is_from_me, mess_hand_chat_join.date as \'date\', mess_hand_chat_join.date_read as date_read, mess_hand_chat_join.date_delivered as date_delivered, chat.ROWID as chat_id, chat.room_name as room_name FROM (SELECT * FROM (SELECT message.ROWID as mess_ROWID, handle.id as id, message.text as text, message.service as service, message.cache_roomnames as cache_roomnames, message.is_from_me as is_from_me, message.date as \'date\', message.date_read as date_read, message.date_delivered as date_delivered FROM message LEFT JOIN handle ON message.handle_id = handle.ROWID) as message_info INNER JOIN chat_message_join on message_info.mess_ROWID = chat_message_join.message_id) as mess_hand_chat_join INNER JOIN chat on mess_hand_chat_join.chat_id = chat.ROWID) as message_chat_info LEFT JOIN message_attachment_join on message_chat_info.message_id = message_attachment_join.message_id) as message_chat_att_join LEFT JOIN attachment on message_chat_att_join.attachment_id = attachment.ROWID WHERE cache_roomnames = \'' + cache_roomname + '\' ORDER BY message_chat_att_join.date ASC;'
            db_cursor.execute(group_messages_query)
            all_messages = db_cursor.fetchall()

            # For each message create a row in the table with the message information
            for message in all_messages:
                # SQL Response column order -> [0,message_id][1,id][2,text][3,service][4,cache_roomnames][5,is_from_me][6,date][7,date_read][8,date_delivered][9,chat_id][10,room_name][11,message_id:1][12,attachment_id][13,ROWID][14,guid][15,created_date][16,start_date][17,filename][18,uti][19,mime_type][20,transfer_state][21,is_outgoing][22,user_info][23,transfer_name][24,total_bytes][25,is_sticker][26,sticker_user_info][27,attribution_info][28,hide_attachment][29,ck_sync_state][30,ck_server_change_token_blob][31,ck_record_id][32,original_guid]
                phone_num = message[1]
                text = message[2]
                service = message[3]
                is_from_me = message[5]
                date_timestamp = message[6]
                room_name = message[10]
                attachment_filename = message[17]
                mime_type = message[19]

                lines_written += 1
                # Print out the message as a row in the table
                add_row_to_table(new_file, backup_path, destination_path, phone_num, text, service, is_from_me, date_timestamp, attachment_filename, mime_type, group=True)

            # End html file
            new_file.write('</body></html>')

            # If no lines written in html (due to no messages sent/recieved), just delete the created file
            if lines_written < 1:
                os.remove(new_html_filename)

            # Update Progress Bar before doing next group chat
            status_index += 1
            printProgressBar(status_index, total_tasks, prefix = 'Progress:', suffix = 'Complete', length = 50)


# Adds a single message as a row in the html table
## new_file: html file we are writing the messages to
## backup_path: path to the iOS backup (used to locate the attachments)
## destination_path: path specified where files will be created
## phone_num: phone number (or apple id, etc.) of user who sent this message
## message: the message's content (actual text)
## service: which service the text was sent over -- SMS or iMessage
## is_from_me: 0 if user received message, 1 if user sent message
## date_timestamp: timestamp of when message was sent/received
## attachment_filename: if the message includes an attachment, this is the path/filename (can be None)
## mime_type: if there is an attachment, this is the attachment's mime_type (e.g. image/gif, video/mp4...)
## group: Boolean specifying if this function is being used in a group chat or single chat context (If used in group chat context the phone number is added to each message to make it clear who sent each message)
## returns: nothing
def add_row_to_table(new_file, backup_path, destination_path, phone_num, message, service, is_from_me, date_timestamp, attachment_filename, mime_type, group=False):
      new_file.write('<tr>')

      # Message sent datetime stamp
      new_file.write('<td style=\"text-align: right;\">' + str(convert_date_timestamp(date_timestamp)) + '</td>')

      # The message text
      if message is not None:
          # If there aren't any ascii characters in a message, assume it's an attachment
          if ((all(ord(char) > 127 for char in message)) or (all(ord(char) < 32 for char in message))):
              message = '<strong>*Attachment*</strong>'

          # Message Sender info
          if is_from_me:
              # If the user sent the message, then make the message blue if iMessage or green if SMS
              if str(service) == 'iMessage':
                  color = '#2184f7'
              else:
                  color = '#1eaf32'
              new_file.write('<td style=\"background-color:' + color + '; color: white;\">' + message.encode('utf-8', errors='replace') + '</td>')
          else:
              # If using this function in group context, add the phone number which sent the message to the message
              if group:
                  new_file.write('<td style=\"background-color: #b8b8be;\"><small><i>(Sent By: ' + phone_num.encode('utf-8', errors='replace') + ')</i></small>' + message.encode('utf-8', errors='replace') + '</td>')
              else:
                  new_file.write('<td style=\"background-color: #b8b8be;\">' + message.encode('utf-8', errors='replace') + '</td>')

      # Add the attachment (if there is one)
      if attachment_filename is not None:
          write_attachment_file(new_file, attachment_filename, mime_type, backup_path, destination_path)
      else:
          new_file.write('<td></td>')
      new_file.write('</tr>')


# Convert date from iOS Message timestamp
# (apple's iOS backup calculates date from 1/1/2001 whereas unix is 1970, therefore we add 978307200 to compensate for this difference)
# For whatever reason, it is also calculated down to the 1/1000000000 of a second... so we convert it to seconds)
### returns: converted time as string
def convert_date_timestamp(original_date_timestamp):
  return datetime.datetime.fromtimestamp(original_date_timestamp/1000000000 + 978307200).strftime("%m/%d/%Y %H:%M:%S")


# Writes the attachment as a cell in the html table
## new_file: the html file to write to
## filename: unhashed filename from iOS message backup sql db
## mime_type: the mime_type of the attachment (e.g. image/gif, video/mp4, etc.)
## backup_path: path to the iOS backup
## destination_path: path to the destination where we are putting the html files (we will also copy the attachments here)
### returns: nothing
def write_attachment_file(new_file, filename, mime_type, backup_path, destination_path):
  # Find hashed file in the backup folder
  ## Filenames are given using relative path, change this to the mobile format of MediaDomain-Library
  attachment_filename = filename.replace('~/Library', 'MediaDomain-Library')
  ## Take the sha1 hash of the filename to find the hashed filename used in the backup
  hashed_filename = hashlib.sha1(attachment_filename).hexdigest()
  ## The backup also sorts each file into another folder by the first two letters in the filename
  hashed_folder = hashed_filename[:2]
  ## Make a complete path to the hashed attachment file
  attachment_filename = backup_path + '/' + hashed_folder + '/' + hashed_filename
  ## Create the path where we will put the attachments in our backup
  destination_attachments_path = destination_path + '/attachments'
  ## Create the full destination filename with path for this attachment file
  destination_filename = destination_attachments_path + '/' + hashed_filename

  # Create an attachments folder in our destination path if we haven't already
  if not os.path.exists(destination_attachments_path):
      os.makedirs(destination_attachments_path)

  # Add extension to video files by mime_type. This will allow them to play in browser. (Images seem to work without adding an extension)
  if mime_type is not None and mime_type == 'video/mp4':
      destination_filename = destination_filename + '.mp4'
  elif mime_type is not None and mime_type == 'video/quicktime':
      destination_filename = destination_filename + '.mov'

  # Copy attachment to destination folder so we can still reference the file even if the original backup is deleted
  if os.path.exists(attachment_filename):
      shutil.copyfile(attachment_filename, destination_filename)

      # Write out attachment file to the html table using the appropriate tag. If it isn't an image or video, just put a link to the file path
      if mime_type is not None and mime_type[:5] == 'image':
          new_file.write('<td><img src=\"' + destination_filename + '\"></td>')
      elif mime_type is not None and mime_type[:5] == 'video':
          new_file.write('<td><video controls><source src=\"' + destination_filename + '\"; type=\"' + mime_type + '\";>Your browser does not support the video tag.</video></td>')
      elif mime_type is not None:
          new_file.write('<td><a href=\"' + destination_filename + '\">Mime-Type: ' + mime_type + ' | Source: ' + destination_filename + '</a></td>')
      else:
          new_file.write('<td><a href=\"' + destination_filename + '\">Mime-Type: No Type Specified | Source: ' + destination_filename + '</a></td>')
  else:
      # Something went wrong... likely the attachment was deleted
      new_file.write('<td></td>')


# Find the latest iTunes iOS backup
### returns: the file containing the latest iTunes iOS backup
def get_latest_iOS_backup_path():
    list_of_files = glob.glob(os.path.expanduser('~/Library/Application Support/MobileSync/Backup/')+'*')
    latest_file = max(list_of_files, key=os.path.getctime)
    return latest_file


# Writes to file the html header information including css styling
## file: html file to write to
def write_html_header(file):
    file.write('<html><head><style>table{width:100%;}td,th{border-radius:10px; font-family: "Verdana", Sans-serif; max-width:200px; padding: 8px;}img{max-width: 200px}video{max-width:200px}}</style></head><body>')


# Print iterations progress -- This 'open source' code taken from Stackoverflow user Greenstick --> https://stackoverflow.com/a/34325723
def printProgressBar (iteration, total, prefix = '', suffix = '', decimals = 1, length = 100, fill = '█'):
    """
    Call in a loop to create terminal progress bar
    @params:
        iteration   - Required  : current iteration (Int)
        total       - Required  : total iterations (Int)
        prefix      - Optional  : prefix string (Str)
        suffix      - Optional  : suffix string (Str)
        decimals    - Optional  : positive number of decimals in percent complete (Int)
        length      - Optional  : character length of bar (Int)
        fill        - Optional  : bar fill character (Str)
    """
    percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
    filledLength = int(length * iteration // total)
    bar = fill * filledLength + '-' * (length - filledLength)
    print('\r%s |%s| %s%% %s' % (prefix, bar, percent, suffix), end = '\r')
    # Print New Line on Complete
    if iteration == total:
        print()
    sys.stdout.flush()


if __name__ == "__main__":
    main()
