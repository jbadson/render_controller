import React, { Component } from 'react';
import './App.css';
import JobInput from './JobInput';
import QueuePane from './QueuePane';
import JobStatusPane from './JobStatus';

/* TODO:
- Consider composing JobStatusBox into queue when open
  - Can click title bar to close
  - Query all data all the time and pass as props
  - Otherwise make back button work or some other good way to switch back to queue view.
  ^-This might actually look nice to go back to two-pane but with this styling.
- Settings popup/menu
  - Should show autostart status and modify, poll interval?
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

  renderContentPane() {
    if (this.state.showInputPane) {
      return (
        <JobInput
          path="/"
          url={API_CONNECT}
          renderNodes={this.state.renderNodes}
          onClose={this.toggleInputPane}
        />
      )
    } else if (this.state.selectedJob) {
      // FIXME: Select correct default and don't break if queue is empty
      return (
        <JobStatusPane
          jobId={this.state.selectedJob}
          url={API_CONNECT}
          pollInterval={POLL_INTERVAL}
        />
      )
    }
    return <p>No data</p>
  }

  render() {
    return (
      <ul>
        <li className="layout-row">
          <button className="left" onClick={this.toggleInputPane}>New</button>
          <p className="right">Settings</p>
        </li>
        <li className="layout-row">
          <div className="sidebar">
            <QueuePane
              url={API_CONNECT}
              pollInterval={POLL_INTERVAL}
              onJobClick={this.selectJob}
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
