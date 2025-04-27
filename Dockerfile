FROM mysql:latest

# Set the MySQL root password
ENV MYSQL_ROOT_PASSWORD=root

# Allow connections only from the internal 192.168 NAT
RUN echo "bind-address = 0.0.0.0" >> /etc/mysql/my.cnf
RUN sed -i 's/127.0.0.1/192.168.0.0/' /etc/mysql/my.cnf

# Create the directory for FLAC files
RUN mkdir -p /flac

# Grant permissions for the directory
RUN chown -R mysql:mysql /flac

# Set the working directory
WORKDIR /flac

# Expose MySQL port
EXPOSE 3306
