const fs = require('fs');
const database = process.env.MONGODB_DATABASE;
const username = process.env.MONGODB_USERNAME;
if (!database || ['admin', 'config', 'local'].includes(database) || !username) {
  console.error('Set an application database and username; system databases are not supported.');
  quit(1);
}
const readSecret = path => fs.readFileSync(path, 'utf8').replace(/[\r\n]+$/, '');
const adminPassword = readSecret(process.env.MONGO_INITDB_ROOT_PASSWORD_FILE);
const appPassword = readSecret(process.env.MONGODB_PASSWORD_FILE);
if (!appPassword) {
  console.error('The application database password must not be empty.');
  quit(1);
}
const credentials = `${encodeURIComponent(process.env.MONGO_INITDB_ROOT_USERNAME)}:${encodeURIComponent(adminPassword)}`;
let phase = 'connect';
let lastFailure = 'not ready';
for (let attempt = 0; attempt < 60; attempt++) {
  try {
    phase = 'connect';
    const connection = new Mongo(`mongodb://${credentials}@mongo:27017/admin?directConnection=true&serverSelectionTimeoutMS=2000`);
    const admin = connection.getDB('admin');
    phase = 'replica status';
    let status;
    try {
      status = admin.runCommand({replSetGetStatus: 1});
    } catch (error) {
      if (error.code !== 94) throw error;
      status = {ok: 0, code: 94};
    }
    if (status.ok !== 1) {
      if (status.code !== 94) throw new Error('Replica set status failed');
      phase = 'replica initialisation';
      const initiated = admin.runCommand({replSetInitiate: {_id: 'rs01', members: [{_id: 0, host: 'mongo:27017'}]}});
      if (initiated.ok !== 1) throw new Error('Replica set initialisation failed');
    }
    if (!admin.runCommand({hello: 1}).isWritablePrimary) {
      sleep(1000);
      continue;
    }
    const app = connection.getDB(database);
    phase = 'application user';
    if (!app.getUser(username)) {
      app.createUser({user: username, pwd: appPassword, roles: [{role: 'readWrite', db: database}],
        mechanisms: ['SCRAM-SHA-1', 'SCRAM-SHA-256']});
    }
    const appCredentials = `${encodeURIComponent(username)}:${encodeURIComponent(appPassword)}`;
    phase = 'application authentication';
    const check = new Mongo(`mongodb://${appCredentials}@mongo:27017/${encodeURIComponent(database)}?replicaSet=rs01&serverSelectionTimeoutMS=3000`);
    check.getDB(database).runCommand({ping: 1});
    print('MongoDB replica set and application user are ready.');
    quit(0);
  } catch (error) {
    lastFailure = `${phase}: ${error.codeName || error.name || 'unknown error'}`;
    sleep(1000);
  }
}
console.error(`MongoDB bootstrap failed (${lastFailure}). Check database logs and credentials; existing user passwords are not changed automatically.`);
quit(1);
