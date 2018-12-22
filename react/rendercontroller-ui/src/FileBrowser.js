import React, { Component } from 'react';
import './FileBrowser.css';
import axios from 'axios';
import { fmtUnixTimestamp } from './util';


/**
 * A file browser widget for navigating the server-side filesystem.
 * @param {string} path - Initial directory to list on server.
 * @param {string} url - URL of API
 * @param {function} onFileClick - Action to take when a file is clicked.
 */
class FileBrowser extends Component {
  constructor(props) {
    super(props);
    this.state = {
      path: null,
      fileList: [],
      pathHistory: [],
      error: null,
    };
    this.onFileClick = props.onFileClick.bind(this);
    this.handleDirClick = this.handleDirClick.bind(this);
    this.handleBackClick = this.handleBackClick.bind(this);
  }

  getDirContents(path) {
    return axios.post(this.props.url, {"path": path});
  }

  componentDidMount() {
    this.handleDirClick(this.props.path);
  }

  handleDirClick(path) {
    this.getDirContents(path)
      .then(
        (result) => {
          this.setState(state => {
            const history = state.pathHistory;
            return ({
              fileList: result.data.contents,
              pathHistory: history.concat([state.path]),
              path: result.data.current,
            })
          });
        },
        (error) => {
          this.setState({error: error});
        },
      );
  }

  handleBackClick() {
    const history = this.state.pathHistory;
    const path = history[history.length - 1]
    if (!path) {
      return;
    }
    this.getDirContents(path).then(
      (result) => {
        this.setState({
          fileList: result.data.contents,
          pathHistory: history.slice(0, history.length -1),
          path: path,
        });
      },
      (error) => {
        this.setState({error: error});
      },
    );
  }

  renderLine(line) {
    // Do not show hidden files
    if (line.name.startsWith(".")) {
      return;
    }
    // Convert mtime
    const mtime = fmtUnixTimestamp(line.mtime);
    // Format based on file type
    let icon = "file_sm.png";
    let className = "fb";
    let handler;
    if (line.type === "d") {
      className += "-dir";
      icon = "folder_sm.png";
      handler = this.handleDirClick;
    } else {
      // Treat symlinks as files because we can't tell what they point to.
      className += "-file";
      handler = this.onFileClick;
    }
    return(
      <li
          className="fb-row"
          onClick={() => handler(line.path)}
          key={line.path}
      >
        <div className={className}>
          <img src={icon} alt="" className="fb-icon" />{line.name}
          <span className="right">{mtime.toString()}</span>
        </div>
      </li>
    );
  }

  renderBackButton() {
    let className = "fb-back-button";
    if (!this.state.pathHistory[this.state.pathHistory.length - 1]) {
      className += "-disabled";
    }
    return (
      <span className={className} onClick={this.handleBackClick}>
        &#8617;
      </span>
    )
  }

  render() {
    const { fileList, error } = this.state;
    if (error) {
      return <p>FileBrowser load failed: {error.message}</p>
    }
    return (
      <ul>
        <li className="fb-row">
          <div className="fb-pathbar">
            {this.renderBackButton()} {this.state.path}
          </div>
        </li>
        <li className="fb-row">
          <div className="fb-labels">
            Name <span className="right">Date Modified</span>
          </div>
        </li>
        <li className="fb-row">
          <div className="fb-inner" >
          <ul>
            {fileList.map(line => this.renderLine(line))}
          </ul>
          </div>
        </li>
      </ul>
    );
  }
}


/**
 * Displays FileBrowser in a popup overlay.
 * @param {string} path - Initial directory to list on server.
 * @param {string} url - URL to API endpoint
 * @param {function} onFileClick - Action to take when a file is clicked.
 * @param {function} onClose - Action to take when window is closed.
 */
class FileBrowserPopup extends Component {
  constructor(props) {
    super(props);
    this.node = React.createRef();
    this.handleClick = this.handleClick.bind(this);
  }

  componentWillMount() {
    document.addEventListener('mousedown', this.handleClick, false);
  }

  componentWillUnmount() {
    document.removeEventListener('mousedown', this.handleClick, false);
  }

  handleClick(event) {
    if (this.node.current.contains(event.target)){
      // Ingore clicks inside this component
      return;
    }
    this.props.onClose();
  }

  render() {
  return (
      <div className="fb-container" ref={this.node}>
        <ul>
          <li className="fb-row">
            <div className="fb-header">
              Select project file on file server
              <div className="fb-closebutton" onClick={this.props.onClose}>X</div>
            </div>
          </li>
          <li className="layout-row">
            <FileBrowser
              url={this.props.url}
              path={this.props.path}
              onFileClick={this.props.onFileClick}
            />
          </li>
        </ul>
      </div>
    )
  }
}


export { FileBrowser, FileBrowserPopup };
