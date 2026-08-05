require('dotenv').config();
const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const morgan = require('morgan');
const rateLimit = require('express-rate-limit');

const authRoutes = require('./routes/auth');
const childrenRoutes = require('./routes/children');
const screenTimeRoutes = require('./routes/screen_time');
const appRulesRoutes = require('./routes/app_rules');
const locationRoutes = require('./routes/location');
const activityRoutes = require('./routes/activity');
const webFilterRoutes = require('./routes/web_filter');
const contentFilterRoutes = require('./routes/content_filter');

const app = express();
const PORT = process.env.PORT || 3000;

app.use(helmet());
app.use(cors());
app.use(morgan('combined'));
app.use(express.json({ limit: '10mb' }));

const limiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  max: 100,
  message: { error: 'Too many requests' },
});
app.use('/api', limiter);

app.use('/api/auth', authRoutes);
app.use('/api/children', childrenRoutes);
app.use('/api/screen-time', screenTimeRoutes);
app.use('/api/app-rules', appRulesRoutes);
app.use('/api/location', locationRoutes);
app.use('/api/activity', activityRoutes);
app.use('/api/web-filter', webFilterRoutes);
app.use('/api/content-filter', contentFilterRoutes);

app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() });
});

app.use((err, req, res, next) => {
  console.error('Unhandled error:', err);
  res.status(500).json({ error: 'Internal server error' });
});

app.listen(PORT, () => {
  console.log(`Guardian backend running on port ${PORT}`);
});

module.exports = app;
