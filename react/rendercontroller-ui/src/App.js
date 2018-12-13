import React, { Component } from 'react';
import './App.css';
import axios from 'axios';
import JobInput from './JobInput';
import QueuePane from './QueuePane';
import JobStatusPane from './JobStatus';
import {FileBrowserPopup} from './FileBrowser';

/* TODO:
- Settings popup/menu
  - Should show autostart status and modify, poll interval?
- Order queue boxes by queue position (or queue time)
- Disable (preferably gray out or hide) buttons in irrelevant contexts:
  Enqueue when state != stopped
  Start when state == running
- Tooltips for buttons, especially start, stop, enqueue
- Finish styling
- Review all FIXMEs and TODOs
- Figure out how to package this for distribution
*/

const POLL_INTERVAL = 1000; // Milliseconds
const API_CONNECT = "http://localhost:2020";


class App extends Component {
  constructor(props) {
    super(props);
    this.state = {
      selectedJob: null,
      serverJobs: [],
      error: null,
      showInputPane: false,
    }
    this.selectJob = this.selectJob.bind(this);
    this.toggleInputPane = this.toggleInputPane.bind(this);
  }

  selectJob(jobId) {
    this.setState({selectedJob: jobId})
  }

  toggleInputPane() {
    this.setState(state => ({showInputPane: !state.showInputPane}))
  }

  getUpdate() {
    // Fetch data from server and update UI
    axios.get(API_CONNECT + "/job/summary")
      .then(
        result => {this.setState({serverJobs: result.data})},
        error => {this.setState({error: error})}
      )
      .then(() => {
        // Select first job if none are selected
        const { selectedJob, serverJobs } = this.state;
        if (!selectedJob && serverJobs.length > 0) {
          this.selectJob(serverJobs[0].id);
        }
      }
      )
  }

  componentDidMount() {
    this.getUpdate()
    this.interval = setInterval(() => this.getUpdate(), POLL_INTERVAL);
  }

  componentWillUnmount() {
    clearInterval(this.interval);
  }

  renderContentPane() {
    if (this.state.showInputPane) {
      return (
        <JobInput
          path="/"
          url={API_CONNECT}
          onClose={this.toggleInputPane}
        />
      )
    } else if (this.state.selectedJob) {
      return (
        <JobStatusPane
          jobId={this.state.selectedJob}
          url={API_CONNECT}
          pollInterval={POLL_INTERVAL}
        />
      )
    }
    return <p>No job selected</p>
  }

  render() {
    const { serverJobs, selectedJob, error } = this.state;
    if (error) {
      return <p>Error: {error.message}</p>
    }
    return (
      <ul>
        <li className="layout-row">
          <button className="button-left" onClick={this.toggleInputPane}>New</button>
          <button className="button-right">Settings</button>
        </li>
        <li className="layout-row">
          <div className="sidebar">
            <QueuePane
              serverJobs={serverJobs}
              onJobClick={this.selectJob}
              selectedJob={selectedJob}
            />
          </div>
          <div className="content-pane">
            {this.renderContentPane()}
          </div>
        </li>
      </ul>
    )
  }
}


export default App;

function Browsertest(props) {
  return (
    <FileBrowserPopup url={API_CONNECT + "/storage/ls"} path="/" onFileClick={() => {console.log('clicked')}} onClose={() => {console.log('closed')}} />
  )
}

//export default Browsertest;
