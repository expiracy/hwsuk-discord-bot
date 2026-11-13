const fs = require('fs');
try {
  const password = fs.readFileSync(process.env.MONGO_INITDB_ROOT_PASSWORD_FILE, 'utf8').replace(/[\r\n]+$/, '');
  const user = encodeURIComponent(process.env.MONGO_INITDB_ROOT_USERNAME);
  const connection = new Mongo(`mongodb://${user}:${encodeURIComponent(password)}@127.0.0.1:27017/admin?directConnection=true&serverSelectionTimeoutMS=2000`);
  const admin = connection.getDB('admin');
  const options = admin.runCommand({getCmdLineOpts: 1});
  if (options.parsed?.replication?.replSet !== 'rs01') quit(1);
  quit(admin.runCommand({ping: 1}).ok === 1 ? 0 : 1);
} catch (_) {
  quit(1);
}
