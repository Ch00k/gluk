import urllib
import json
import ConfigParser
import logging as log
import platform
import sys
import os
import tarfile
import subprocess
import smtplib
import xmpp
import socket
import time
import httplib2


"""Setup logging"""
log.basicConfig(filename = '/var/log/gluk.log',
                format='[%(asctime)s]: %(levelname)s: %(message)s',
                datefmt = '%Y-%m-%d, %H:%M:%S',
                level = log.DEBUG)

"""Get configuration options"""
config = ConfigParser.RawConfigParser()
if config.read('gluk.conf') != []:
    pass
else:
    log.critical('Cannot open configuration file')
    sys.exit('Cannot open configuration file')
try:    
    LINODE_API_URL = config.get('LINODE_API', 'url')
    USERNAME = config.get('LINODE_API', 'username')
    PASSWORD = config.get('LINODE_API', 'password')
    
    KERNEL_URL = config.get('KERNEL', 'url')
    KERNEL_TMP_DIR = config.get('KERNEL', 'tmp_directory')
    KERNEL_SRC_DIR = config.get('KERNEL', 'src_directory')
    
    LINODE_NAME = config.get('LINODE', 'name')
    LINODE_CONFIG_PROFILE = config.get('LINODE', 'profile')
    
    ESELECT_EXECUTABLE = config.get('ESELECT', 'executable')
    ESELECT_OPTIONS = config.get('ESELECT', 'options')
    ESELECT_MODULE = config.get('ESELECT', 'module')
    ESELECT_ACTION_LIST = config.get('ESELECT', 'action_list')
    ESELECT_ACTION_SET = config.get('ESELECT', 'action_set')
    
    MODULES_BASEDIR = config.get('MODULES', 'basedir')
    MODULES_FILE = config.get('MODULES', 'file')
    
    MAIL_SERVER = config.get('EMAIL', 'server')
    MAIL_USER = config.get('EMAIL', 'user')
    MAIL_PASSWORD = config.get('EMAIL', 'password')
    MAIL_SENDER = config.get('EMAIL', 'mailfrom')
    MAIL_RECIPIENT = config.get('EMAIL', 'mailto')
    
    JABBER_SERVER = config.get('JABBER', 'server')
    JABBER_LOGIN = config.get('JABBER', 'login')
    JABBER_PASSWORD = config.get('JABBER', 'password')
    JABBER_RECIPIENT = config.get('JABBER', 'jabberto')
except ConfigParser.NoSectionError, error:
    log.critical('Errors reading config file: %s' % error)
    sys.exit('Errors reading config file: %s' % error)
except ConfigParser.NoOptionError, error:
    log.critical('Errors reading config file: %s' % error)
    sys.exit('Errors reading config file: %s' % error)


class HostActions(object):
    def _get_current_kernel(self):
        log.info('Getting host kernel version')
        host_kernel =  platform.release()
        log.info('Host kernel: %s') % host_kernel
        
        return host_kernel
    
    def _get_kernel_branch(self, kernel):
        kernel_branch = kernel.split('-')[0].rpartition('.')[0]
        
        return kernel_branch
    
    def _download_kernel(self, linode_kernel):
        self.kernel_basename = 'linux-%s' % linode_kernel.split('-')[0]
        url = '%s%s.tar.bz2' % (KERNEL_URL, self.kernel_basename)
        self.kernel_tarball_path = '%s%s.tar.bz2' \
                                    % (KERNEL_TMP_DIR,
                                       self.kernel_basename)
        if urllib.urlopen(url).getcode() == 200:
            log.info('Trying to download kernel by the URL \'%s\'' % url) 
            urllib.urlretrieve(url, self.kernel_tarball_path)
        else:
            log.critical('URL \'%s\' is invalid! Exiting' % url)
            sys.exit('URL \'%s\' is invalid! Exiting' % url)
            
    def _extract_kernel(self):
        log.info('Extracting \'%s\' kernel tarball into \'%s\'' \
                  % (self.kernel_tarball_path, KERNEL_SRC_DIR))
        try:
            kernel_tarball = tarfile.open(self.kernel_tarball_path)
            kernel_tarball.extractall(KERNEL_SRC_DIR)
            log.info('Extracted successgully')
        except Exception, error:
            log.error('Could not extract kernel tarball: %s' % error)
            sys.exit('Could not extract kernel tarball: %s' % error)
            
    def _rename_kernel(self, linode_kernel):
            try:
                log.info('Renaming kernel directory from \'%s\' to \'%s\'' \
                         % (self.kernel_basename, linode_kernel))
                os.rename(self.kernel_basename, linode_kernel)
            except Exception, error:
                log.critical('Could not rename kernel directory: %s' % error)
                sys.exit('Could not rename kernel directory: %s' % error)
                
    def _kernel_present(self, linode_kernel):
        command = '%s %s %s %s' \
                  % (ESELECT_EXECUTABLE,
                     ESELECT_OPTIONS,
                     ESELECT_MODULE,
                     ESELECT_ACTION_LIST)
        log.info('Checking with \'eselect\' if kernel source directory for \'%s\' is present' \
                 % (linode_kernel))
        log.info('eselect command: \'%s\'' % command)
        output = subprocess.Popen(command,
                                  shell = True,
                                  stdout = subprocess.PIPE,
                                  sterr = subprocess.PIPE)
        out, err = output.communicate()
        if linode_kernel in out:
            log.info('%s present' % linode_kernel)
            return True
        else:
            log.critical('%s not present' % linode_kernel)
            return False
    
    def _select_kernel(self, linode_kernel):
        if self._kernel_present(linode_kernel):
            command = '%s %s %s %s %s' \
                      % (ESELECT_EXECUTABLE,
                         ESELECT_OPTIONS,
                         ESELECT_MODULE,
                         ESELECT_ACTION_SET,
                         linode_kernel)
            log.info('Trying with eselect to select kernel \'%s\'' % linode_kernel)
            log.info('eselect command: \'%s\'' % command)
            output = subprocess.Popen(command,
                                      shell = True,
                                      stdout = subprocess.PIPE,
                                      stderr = subprocess.PIPE)
            out, err = output.communicate()
            if not err:
                pass
            else:
                log.critical('Could not select kernel \'%s\'' % linode_kernel)
                sys.exit('Could not select kernel \'%s\'' % linode_kernel)
        else:
            sys.exit('%s not present' % linode_kernel)
            
    def _create_modulesdep(self, linode_kernel):
        command = 'mkdir %s%s' % (MODULES_BASEDIR, linode_kernel)
        log.info('Trying trying to create directory \'%s$s\'' % (MODULES_BASEDIR, linode_kernel))
        log.info('Command: \'%s\'' % command)
        output = subprocess.Popen(command,
                                  shell = True,
                                  stdout = subprocess.PIPE,
                                  stderr = subprocess.PIPE)
        out, err = output.communicate()
        if err:
            log.error('Could not create directory \'%s$s\'. \
                       Please create it yourself after reboot' \
                       % (MODULES_BASEDIR, linode_kernel))
    
    def _kernel_versions_equal(self, linode_kernel):
        host_kernel = self._get_current_kernel()
        host_kernel_branch = self._get_kernel_branch(host_kernel)
        linode_kernel_branch = self._get_kernel_branch(linode_kernel)
        if host_kernel_branch != linode_kernel_branch:
            log.critical('Host kernel branch differs from kernel branch, \
                          used in your Linode\'s configuration profile. \
                          Host kernel is of branch %s, Linode\'s kernel \
                          is of branch %s' \
                          % (host_kernel_branch, linode_kernel_branch))
            sys.exit('Host kernel branch differs from kernel branch, \
                      used in your Linode\'s configuration profile. \
                      Host kernel is of branch %s, Linode\'s kernel \
                      is of branch %s' \
                      % (host_kernel_branch, linode_kernel_branch))
            
        if linode_kernel == host_kernel:
            log.info('Host kernel equals Linode\'s kernel. Nothing to do')
            return True
        else:
            log.info('Linode\'s kernel differs from current host kernel. \
                      Going to update')
            return False
        
    @classmethod
    def update_kernel(self, linode_kernel):
        if not self._kernel_versions_equal(linode_kernel):
            self._download_kernel(linode_kernel, KERNEL_TMP_DIR)
            self._extract_kernel()
            self._rename_kernel(linode_kernel)
            self._select_kernel(linode_kernel)
            self._create_modulesdep(linode_kernel)
        else:
            sys.exit('Host kernel equals Linode\'s kernel. Nothing to do')
            


class LinodeAPIClient(object):
    def __init__(self, username, password):
        request_params = {'api_action': 'user.getapikey',
                          'username': username,
                          'password': password
                          }
        url = self._compile_url(request_params)
        self.client = httplib2.Http()
        info, response = self.client.request(url, 'GET')
        response = json.loads(response)
        self.api_key = response['DATA']['API_KEY']
        
    def _compile_url(self, params):
        url_params = params
        query_string = urllib.urlencode(url_params)
        url = '%s?%s' % (LINODE_API_URL, query_string)
        
        return url
    
    def get_kernels(self):
        request_params = {'api_key': self.api_key,
                          'api_action': 'avail.kernels',
                          'isxen': 1
                          }
        url = self._compile_url(request_params)
        info, response = self.client.request(url, 'GET')
        response = json.loads(response)
        kernels = response['DATA']
        
        return kernels
    
    def get_current_kernel(self, linode_name):
        linode_params = self._get_linode_params(linode_name)
        request_params = {'api_key': self.api_key,
                          'api_action': 'linode.config.list',
                          'linodeid': linode_params['linode_id'],
                          'configid': linode_params['linode_config_profile_id']
                          }
        url = self._compile_url(request_params)
        info, response = self.client.request(url, 'GET')
        response = json.loads(response)
        current_kernel_id = response['DATA']['KernelID']
        kernels = self.get_kernels()
        for kernel in kernels:
            if kernel['KERNELID'] == current_kernel_id:
                current_kernel_label = kernel['LABEL']
        if not 'Latest' in current_kernel_label:
            log.critical('You Linode\'s config profile is incorrect. \
                          Please use one of the "Latest" kernels')
            sys.exit('You Linode\'s config profile is incorrect. \
                      Please use one of the "Latest" kernels')
        else:
            current_kernel = current_kernel_label.split('(')[1].split(')')[0]
            
        return current_kernel
    
    def _get_linode_params(self, linode_name):
        linode_params = {}
        request_params = {'api_key': self.api_key,
                          'api_action': 'linode.list'
                          }
        url = self._compile_url(request_params)
        info, response = self.client.request(url, 'GET')
        response = json.loads(response)
        for linode in response['DATA']:
            if linode['LABEL'] == linode_name:
                linode_id = linode['LINODEID']
        linode_params['linode_id'] = linode_id
        request_params = {'api_key': self.api_key,
                          'api_action': 'linode.config.list',
                          'linodeid': linode_id
                          }
        url = self._compile_url(request_params)
        info, response = self.client.request(url, 'GET')
        response = json.loads(response)
        for config_profile in response['DATA']:
            if config_profile['Label'] == LINODE_CONFIG_PROFILE:
                linode_config_profile_id = config_profile['ConfigID']
        linode_params['linode_config_profile_id'] = linode_config_profile_id
        
        return linode_params
    
    def reboot_linode(self, linode_name):
        linode_params = self.get_linode_params(linode_name)
        request_params = {'linodeid': linode_params['linode_id'],
                          'configid': linode_params['linode_config_profile_id']
                          }
        url = self._compile_url(request_params)
        info, response = self.client.request(url, 'GET')
        response = json.loads(response)
        
        
class EmailNotifier(object):
    """Emails notifier class
    """
    def __init__(self, server, user, password):
        """Creates a connection to SMTP server and performs SMTP authentication
        """
        try:
            if int(MAIL_SERVER.split(':')[1]) == 465:
                self.smtp = smtplib.SMTP_SSL(server,
                                             timeout = 15)
            elif int(MAIL_SERVER.split(':')[1]) in (25, 587):
                self.smtp = smtplib.SMTP(server,
                                         timeout = 15)
                try:
                    self.smtp.starttls()
                except smtplib.SMTPException, error:
                    log.warning(error) # not sure if the user should see this
                    pass
            else:
                raise ValueError('Invalid SMTP server port')
        except socket.error, error:
            log.error('Cannot connect to SMTP server: %s: '
                      % (error,
                         server))
            raise
        except ValueError, error:
            log.error('Cannot connect to SMTP server: %s: %s'
                      % (server,
                         error))
            raise
        else:
            if user is not None and password is not None:
                try:
                    self.smtp.login(user = user,
                                    password = password)
                except smtplib.SMTPAuthenticationError, error:
                    log.error('Cannot authenticate on SMTP server: %d, %s'
                              % (error[0],
                                 error[1]))
                    raise
                except smtplib.SMTPException, error:
                    log.error('Cannot authenticate on SMTP server: %s' % error)
                    raise
            
    def send(self, linode_kernel):
        """Compiles an email message and sends it
        """
        headers = ('From: %s\r\n' \
                   'To: %s\r\n' \
                   'Subject: [%s] %s Kernel has beed updated\r\n' \
                   'Content-Type: text/plain; charset=utf-8\r\n\r\n'
                   % (MAIL_SENDER,
                      MAIL_RECIPIENT,
                      platform.node(),
                      time.strftime('%Y-%m-%d')))
        body = '%s kernel has been updated to \'%s\'.' % (platform.node(), linode_kernel)
        message = headers + body
        try:
            log.info('Sending Email message')
            self.smtp.sendmail(from_addr = MAIL_SENDER,
                               to_addrs = MAIL_RECIPIENT,
                               msg = message)
        except smtplib.SMTPRecipientsRefused, error:
            log.error('Cannot send email: %s' % (error))
        
    def disconnect(self):
        """Disconnects from SMTP server
        """
        self.smtp.quit()
        
        
class JabberError(Exception):
    """Jabber exceptions class
    """
    def connect_error(self):
        raise IOError('Cannot connect to Jabber server')
    
    def auth_error(self):
        raise IOError('Cannot authenticate on Jabber server')
    

class JabberNotifier(object):
    """Jabber notifier class
    """
    def __init__(self, server, login, password):
        """Creates a connection to XMPP server and performs user authentication
        """
        self.client = xmpp.Client(server = server.split(':')[0],
                                  port = server.split(':')[1],
                                  debug = [])
        if not self.client.connect():
            try:
                JabberError().connect_error(), error
            except IOError, error:
                log.error('%s: %s' % (error, server))
                raise
                
        else:
            if not self.client.auth(user = login,
                                    password = password,
                                    resource = 'gun'):
                try:
                    JabberError().auth_error(), error
                except IOError, error:
                    log.error(error)
                    raise
            
    def send(self):
        """Sends Jabber message
        """
        body = Message(input_file = OUTPUT_FILE)
        message = body.as_plaintext()
        log.info('Sending Jabber message')
        self.client.send(xmpp.protocol.Message(to = JABBER_RECIPIENT,
                                               body = message))
        
    def disconnect(self):
        """Disconnects from XMPP server
        """
        self.client.disconnect()
    
        
        
if __name__ == '__main__':
    linode_api_client = LinodeAPIClient(USERNAME, PASSWORD)
    linode_kernel = linode_api_client.get_current_kernel(LINODE_NAME)
    HostActions.update_kernel(linode_kernel)
    linode_api_client.reboot_linode(LINODE_NAME)
