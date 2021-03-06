from unittest import mock
from unittest.mock import call

import pytest

from nephos.fabric.crypto import (
    CryptoInfo,
    register_node, enroll_node, create_admin, admin_creds, msp_secrets, admin_msp,
    item_to_secret, id_to_secrets, cacerts_to_secrets,
    setup_nodes, genesis_block, channel_tx, PWD)


class TestRegisterNode:
    @mock.patch('nephos.fabric.crypto.get_pod')
    def test_register_node(self, mock_get_pod):
        mock_executor = mock.Mock()
        mock_get_pod.side_effect = [mock_executor]
        mock_executor.execute.side_effect = [None,  # List identities
                                             None]  # Register identities
        register_node('a-namespace', 'a-ca', 'orderer', 'an-ord', 'a-password')
        mock_get_pod.assert_called_once_with(namespace='a-namespace', release='a-ca', app='hlf-ca', verbose=False)
        mock_executor.execute.assert_has_calls([
            call('fabric-ca-client identity list --id an-ord'),
            call('fabric-ca-client register --id.name an-ord --id.secret a-password --id.type orderer')
        ])

    @mock.patch('nephos.fabric.crypto.get_pod')
    def test_register_node_again(self, mock_get_pod):
        mock_executor = mock.Mock()
        mock_get_pod.side_effect = [mock_executor]
        mock_executor.execute.side_effect = ['an-ord']  # List identities
        register_node('a-namespace', 'a-ca', 'orderer', 'an-ord', 'a-password', verbose=True)
        mock_get_pod.assert_called_once_with(namespace='a-namespace', release='a-ca', app='hlf-ca', verbose=True)
        mock_executor.execute.assert_called_once_with('fabric-ca-client identity list --id an-ord')


class TestEnrollNode:
    OPTS = {'core': {'dir_config': './a_dir'},
            'cas': {'a-ca': {'namespace': 'ca-namespace', 'tls_cert': '/some_msp/tls_cert.pem'}}}

    @mock.patch('nephos.fabric.crypto.ingress_read')
    @mock.patch('nephos.fabric.crypto.execute_until_success')
    def test_enroll_node(self, mock_execute_until_success, mock_ingress_read):
        mock_ingress_read.side_effect = [['an-ingress']]
        enroll_node(self.OPTS, 'a-ca', 'an-ord', 'a-password')
        mock_ingress_read.assert_called_once_with('a-ca-hlf-ca', namespace='ca-namespace', verbose=False)
        mock_execute_until_success.assert_called_once_with(
            'FABRIC_CA_CLIENT_HOME=./a_dir fabric-ca-client enroll ' +
            '-u https://an-ord:a-password@an-ingress -M an-ord_MSP ' +
            '--tls.certfiles /some_msp/tls_cert.pem')

    @mock.patch('nephos.fabric.crypto.path')
    @mock.patch('nephos.fabric.crypto.ingress_read')
    @mock.patch('nephos.fabric.crypto.execute_until_success')
    def test_enroll_node_again(self, mock_execute_until_success, mock_ingress_read, mock_path):
        mock_ingress_read.side_effect =[['an-ingress']]
        mock_path.join.side_effect = ['./a_dir/a-peer_MSP']
        mock_path.isdir.side_effect = [True]
        enroll_node(self.OPTS, 'a-ca', 'a-peer', 'a-password')
        mock_ingress_read.assert_called_once_with('a-ca-hlf-ca', namespace='ca-namespace', verbose=False)
        mock_execute_until_success.assert_not_called()

    @mock.patch('nephos.fabric.crypto.ingress_read')
    @mock.patch('nephos.fabric.crypto.execute_until_success')
    def test_enroll_verbose(self, mock_execute_until_success, mock_ingress_read):
        mock_ingress_read.side_effect =[['an-ingress']]
        enroll_node(self.OPTS, 'a-ca', 'a-peer', 'a-password', verbose=True)
        mock_ingress_read.assert_called_once_with('a-ca-hlf-ca', namespace='ca-namespace', verbose=True)
        mock_execute_until_success.assert_called_once_with(
            'FABRIC_CA_CLIENT_HOME=./a_dir fabric-ca-client enroll ' +
            '-u https://a-peer:a-password@an-ingress -M a-peer_MSP ' +
            '--tls.certfiles /some_msp/tls_cert.pem')


# TODO: Add verbosity test
class TestCreateAdmin:
    OPTS = {
        'core': {'dir_config': './a_dir'},
        'msps': {'a_MSP': {'ca': 'a-ca',
                           'org_admin': 'an_admin',
                           'org_adminpw': 'a_password'}
                 },
        'cas': {'a-ca': {'namespace': 'ca-namespace', 'tls_cert': './a_cert.pem'}}
    }

    @mock.patch('nephos.fabric.crypto.ingress_read')
    @mock.patch('nephos.fabric.crypto.get_pod')
    @mock.patch('nephos.fabric.crypto.execute')
    def test_ca_create_admin(self, mock_execute, mock_get_pod, mock_ingress_read):
        mock_pod_exec = mock.Mock()
        mock_pod_exec.execute.side_effect = [
            None,  # List CA identities
            'registration'
        ]
        mock_get_pod.side_effect = [mock_pod_exec]
        mock_ingress_read.side_effect = [['an-ingress']]
        create_admin(self.OPTS, 'a_MSP')
        mock_get_pod.assert_called_once_with(
            namespace='ca-namespace', release='a-ca', app='hlf-ca', verbose=False)
        mock_ingress_read.assert_called_once_with(
            'a-ca-hlf-ca', namespace='ca-namespace', verbose=False)
        mock_pod_exec.execute.assert_has_calls([
            call('fabric-ca-client identity list --id an_admin'),
            call("fabric-ca-client register --id.name an_admin --id.secret a_password --id.attrs 'admin=true:ecert'")
        ])
        mock_execute.assert_called_once_with(
            'FABRIC_CA_CLIENT_HOME=./a_dir fabric-ca-client enroll ' +
            '-u https://an_admin:a_password@an-ingress -M a_MSP --tls.certfiles ./a_cert.pem', verbose=False)


class TestAdminCreds:
    OPTS = {
        'msps': {
            'an-msp': {
                'namespace': 'msp-namespace', 'org_admin': 'an-admin'
            }
        }
    }

    @mock.patch('nephos.fabric.crypto.credentials_secret')
    def test_admin_creds(self, mock_credentials_secret):
        mock_credentials_secret.side_effect = [{'CA_PASSWORD': 'a_password'}]
        admin_creds(self.OPTS, 'an-msp')
        mock_credentials_secret.assert_called_once_with(
            'hlf--an-admin-admincred', 'msp-namespace', username='an-admin', password=None, verbose=False)
        assert self.OPTS['msps']['an-msp'].get('org_adminpw') == 'a_password'

    @mock.patch('nephos.fabric.crypto.credentials_secret')
    def test_admin_creds_again(self, mock_credentials_secret):
        mock_credentials_secret.side_effect = [{'CA_PASSWORD': 'a_password'}]
        admin_creds(self.OPTS, 'an-msp', verbose=True)
        mock_credentials_secret.assert_called_once_with(
            'hlf--an-admin-admincred', 'msp-namespace', username='an-admin', password='a_password', verbose=True)
        assert self.OPTS['msps']['an-msp'].get('org_adminpw') == 'a_password'


# TODO: Add verbose test
class TestMspSecrets:
    OPTS = {
        'core': {'dir_config': './a_dir'},
        'msps': {
            'a_MSP': {
                'namespace': 'msp-namespace', 'org_admin': 'an-admin'
            }
        }
    }

    @mock.patch('nephos.fabric.crypto.shutil')
    @mock.patch('nephos.fabric.crypto.makedirs')
    @mock.patch('nephos.fabric.crypto.id_to_secrets')
    @mock.patch('nephos.fabric.crypto.cacerts_to_secrets')
    def test_msp_secrets(self, mock_cacerts_to_secrets, mock_id_to_secrets, mock_makedirs, mock_shutil):
        msp_secrets(self.OPTS, 'a_MSP')
        mock_makedirs.assert_called_once_with('./a_dir/a_MSP/admincerts')
        mock_shutil.copy.assert_called_once_with('./a_dir/a_MSP/signcerts/cert.pem', './a_dir/a_MSP/admincerts/cert.pem')
        mock_cacerts_to_secrets.assert_called_once_with(
            'msp-namespace', './a_dir/a_MSP', 'an-admin', verbose=False)
        mock_id_to_secrets.assert_called_once_with(
            'msp-namespace', './a_dir/a_MSP', 'an-admin', verbose=False)


# TODO: Add verbosity test
class TestAdminMsp:
    OPTS = {
        'core': {'dir_config': './a-dir'},
        'msps': {
            'an-msp': {
                'namespace': 'msp-namespace', 'ca': 'a-ca', 'org_admin': 'an_admin'
            }
        }
    }

    @mock.patch('nephos.fabric.crypto.ns_create')
    @mock.patch('nephos.fabric.crypto.msp_secrets')
    @mock.patch('nephos.fabric.crypto.create_admin')
    @mock.patch('nephos.fabric.crypto.admin_creds')
    def test_admin_msp(self, mock_ca_creds,  mock_create_admin, mock_msp_secrets, mock_ns_create):
        admin_msp(self.OPTS, 'an-msp')
        mock_ns_create.assert_called_once_with('msp-namespace', verbose=False)
        mock_ca_creds.assert_called_once_with(
            self.OPTS, 'an-msp', verbose=False)
        mock_create_admin.assert_called_once_with(self.OPTS, 'an-msp', verbose=False)
        mock_msp_secrets.assert_called_once_with(self.OPTS, 'an-msp', verbose=False)


class TestItemToSecret:
    @mock.patch('nephos.fabric.crypto.print')
    @mock.patch('nephos.fabric.crypto.crypto_secret')
    def test_item_to_secret(self, mock_crypto_secret, mock_print):
        item_to_secret('msp-namespace', './a_dir', 'a-user', CryptoInfo('a-type', 'a_subfolder', 'a-key', True))
        mock_crypto_secret.assert_called_once_with(
            'hlf--a-user-a-type', 'msp-namespace',
            file_path='./a_dir/a_subfolder', key='a-key', verbose=False)
        mock_print.assert_not_called()

    @mock.patch('nephos.fabric.crypto.print')
    @mock.patch('nephos.fabric.crypto.crypto_secret')
    def test_item_to_secret_unrequired(self, mock_crypto_secret, mock_print):
        mock_crypto_secret.side_effect = [Exception()]
        item_to_secret('msp-namespace', './a_dir', 'a-user', CryptoInfo('a-type', 'a_subfolder', 'a-key', False))
        mock_crypto_secret.assert_called_once_with(
            'hlf--a-user-a-type', 'msp-namespace',
            file_path='./a_dir/a_subfolder', key='a-key', verbose=False)
        mock_print.assert_called_once_with(
            'No ./a_dir/a_subfolder found, so secret "hlf--a-user-a-type" was not created')

    @mock.patch('nephos.fabric.crypto.print')
    @mock.patch('nephos.fabric.crypto.crypto_secret')
    def test_item_to_secret_failed(self, mock_crypto_secret, mock_print):
        mock_crypto_secret.side_effect = [Exception()]
        with pytest.raises(Exception):
            item_to_secret('msp-namespace', './a_dir', 'a-user', CryptoInfo('a-type', 'a_subfolder', 'a-key', True))
        mock_crypto_secret.assert_called_once_with(
            'hlf--a-user-a-type', 'msp-namespace', file_path='./a_dir/a_subfolder', key='a-key', verbose=False)
        mock_print.assert_not_called()


class TestIdToSecrets:
    @mock.patch('nephos.fabric.crypto.item_to_secret')
    def test_id_to_secrets(self, mock_item_to_secret):
        mock_item_to_secret.side_effect = [None, None]
        id_to_secrets('msp-namespace', './a_dir', 'a-user')
        mock_item_to_secret.assert_has_calls([
            call('msp-namespace', './a_dir', 'a-user',
                 CryptoInfo('idcert', 'signcerts', 'cert.pem', True), verbose=False),
            call('msp-namespace', './a_dir', 'a-user',
                 CryptoInfo('idkey', 'keystore', 'key.pem', True), verbose=False),
        ])

    @mock.patch('nephos.fabric.crypto.item_to_secret')
    def test_id_to_secrets_nocert(self, mock_item_to_secret):
        mock_item_to_secret.side_effect = [Exception()]
        with pytest.raises(Exception):
            id_to_secrets('msp-namespace', './a_dir', 'a-user', verbose=True)
        mock_item_to_secret.assert_called_once_with(
            'msp-namespace', './a_dir', 'a-user',
            CryptoInfo('idcert', 'signcerts', 'cert.pem', True), verbose=True)


class TestCaCertsToSecrets:
    @mock.patch('nephos.fabric.crypto.item_to_secret')
    def test_cacerts_to_secrets(self, mock_item_to_secret):
        mock_item_to_secret.side_effect = [None, None]
        cacerts_to_secrets('msp-namespace', './a_dir', 'a-user')
        mock_item_to_secret.assert_has_calls([
            call('msp-namespace', './a_dir', 'a-user',
                 CryptoInfo('cacert', 'cacerts', 'cacert.pem', True), verbose=False),
            call('msp-namespace', './a_dir', 'a-user',
                 CryptoInfo('caintcert', 'intermediatecerts', 'intermediatecacert.pem', False), verbose=False),
        ])

    @mock.patch('nephos.fabric.crypto.item_to_secret')
    def test_cacerts_to_secrets_nocacert(self, mock_item_to_secret):
        mock_item_to_secret.side_effect = [Exception()]
        with pytest.raises(Exception):
            cacerts_to_secrets('msp-namespace', './a_dir', 'a-user')
        mock_item_to_secret.assert_called_once_with(
            'msp-namespace', './a_dir', 'a-user',
            CryptoInfo('cacert', 'cacerts', 'cacert.pem', True), verbose=False)


class TestSetupNodes:
    OPTS = {
        'cas': {
            'ca-ord': {'namespace': 'ca-namespace'},
            'ca-peer': {'namespace': 'ca-namespace'}
        },
        'msps': {
            'ord_MSP': {'ca': 'ca-ord', 'namespace': 'ord-namespace'},
            'peer_MSP': {'ca': 'ca-peer', 'namespace': 'peer-namespace'}
        },
        'peers': {'names': ['peer0', 'peer1'], 'msp': 'peer_MSP'},
        'orderers': {'names': ['ord0'], 'msp': 'ord_MSP'}
    }

    @mock.patch('nephos.fabric.crypto.register_node')
    @mock.patch('nephos.fabric.crypto.enroll_node')
    @mock.patch('nephos.fabric.crypto.id_to_secrets')
    @mock.patch('nephos.fabric.crypto.credentials_secret')
    def test_setup_nodes(self, mock_credentials_secret, mock_crypto_to_secrets,
                         mock_enroll_node, mock_register_node):
        mock_credentials_secret.side_effect = [{'CA_USERNAME': 'peer0', 'CA_PASSWORD': 'peer0-pw'},
                                               {'CA_USERNAME': 'peer1', 'CA_PASSWORD': 'peer1-pw'}]
        mock_enroll_node.side_effect = ['./peer0_MSP', './peer1_MSP']
        setup_nodes(self.OPTS, 'peer')
        mock_credentials_secret.assert_has_calls([
            call('hlf--peer0-cred', 'peer-namespace', username='peer0', verbose=False),
            call('hlf--peer1-cred', 'peer-namespace', username='peer1', verbose=False)
        ])
        mock_register_node.assert_has_calls([
            call('ca-namespace', 'ca-peer', 'peer', 'peer0', 'peer0-pw', verbose=False),
            call('ca-namespace', 'ca-peer', 'peer', 'peer1', 'peer1-pw', verbose=False)
        ])
        mock_enroll_node.assert_has_calls([
            call(self.OPTS, 'ca-peer', 'peer0', 'peer0-pw', verbose=False),
            call(self.OPTS, 'ca-peer', 'peer1', 'peer1-pw', verbose=False)
        ])
        mock_crypto_to_secrets.assert_has_calls([
            call(namespace='peer-namespace', msp_path='./peer0_MSP', user='peer0', verbose=False),
            call(namespace='peer-namespace', msp_path='./peer1_MSP', user='peer1', verbose=False)
        ])

    @mock.patch('nephos.fabric.crypto.register_node')
    @mock.patch('nephos.fabric.crypto.enroll_node')
    @mock.patch('nephos.fabric.crypto.id_to_secrets')
    @mock.patch('nephos.fabric.crypto.credentials_secret')
    def test_setup_nodes_ord(self, mock_credentials_secret, mock_crypto_to_secrets,
                         mock_enroll_node, mock_register_node):
        mock_credentials_secret.side_effect = [{'CA_USERNAME': 'ord0', 'CA_PASSWORD': 'ord0-pw'}]
        mock_enroll_node.side_effect = ['./ord0_MSP']
        setup_nodes(self.OPTS, 'orderer')
        mock_credentials_secret.assert_has_calls([
            call('hlf--ord0-cred', 'ord-namespace', username='ord0', verbose=False)
        ])
        mock_register_node.assert_has_calls([
            call('ca-namespace', 'ca-ord', 'orderer', 'ord0', 'ord0-pw', verbose=False)
        ])
        mock_enroll_node.assert_has_calls([
            call(self.OPTS, 'ca-ord', 'ord0', 'ord0-pw', verbose=False)
        ])
        mock_crypto_to_secrets.assert_has_calls([
            call(namespace='ord-namespace', msp_path='./ord0_MSP', user='ord0', verbose=False)
        ])


class TestGenesisBlock:
    OPTS = {
        'core': {'dir_config': './a_dir'},
        'msps': {'ord_MSP': {'namespace': 'ord-namespace'}},
        'orderers': {'secret_genesis': 'a-genesis-secret', 'msp': 'ord_MSP'}
    }

    @mock.patch('nephos.fabric.crypto.secret_from_file')
    @mock.patch('nephos.fabric.crypto.print')
    @mock.patch('nephos.fabric.crypto.path')
    @mock.patch('nephos.fabric.crypto.execute')
    @mock.patch('nephos.fabric.crypto.chdir')
    def test_blocks(self, mock_chdir, mock_execute, mock_path, mock_print, mock_secret_from_file):
        mock_path.exists.side_effect = [False, False]
        genesis_block(self.OPTS)
        mock_chdir.assert_has_calls([
            call('./a_dir'),
            call(PWD)
        ])
        mock_path.exists.assert_called_once_with('genesis.block')
        mock_execute.assert_called_once_with(
            'configtxgen -profile OrdererGenesis -outputBlock genesis.block', verbose=False)
        mock_print.assert_not_called()
        mock_secret_from_file.assert_called_once_with(
            secret='a-genesis-secret', namespace='ord-namespace',
            key='genesis.block', filename='genesis.block', verbose=False)

    @mock.patch('nephos.fabric.crypto.secret_from_file')
    @mock.patch('nephos.fabric.crypto.print')
    @mock.patch('nephos.fabric.crypto.path')
    @mock.patch('nephos.fabric.crypto.execute')
    @mock.patch('nephos.fabric.crypto.chdir')
    def test_again(self, mock_chdir, mock_execute, mock_path, mock_print, mock_secret_from_file):
        mock_path.exists.side_effect = [True, True]
        genesis_block(self.OPTS, True)
        mock_chdir.assert_has_calls([
            call('./a_dir'),
            call(PWD)
        ])
        mock_path.exists.assert_called_once_with('genesis.block')
        mock_execute.assert_not_called()
        mock_print.assert_called_once_with('genesis.block already exists')
        mock_secret_from_file.assert_called_once_with(
            secret='a-genesis-secret', namespace='ord-namespace',
            key='genesis.block', filename='genesis.block', verbose=True)


class TestChannelTx:
    OPTS = {
        'core': {'dir_config': './a_dir'},
        'msps': {'peer_MSP': {'namespace': 'peer-namespace'}},
        'peers': {
            'channel_name': 'a-channel', 'channel_profile': 'AProfile',
            'msp': 'peer_MSP', 'secret_channel': 'a-channel-secret'
        }
    }

    @mock.patch('nephos.fabric.crypto.secret_from_file')
    @mock.patch('nephos.fabric.crypto.print')
    @mock.patch('nephos.fabric.crypto.path')
    @mock.patch('nephos.fabric.crypto.execute')
    @mock.patch('nephos.fabric.crypto.chdir')
    def test_blocks(self, mock_chdir, mock_execute, mock_path, mock_print, mock_secret_from_file):
        mock_path.exists.side_effect = [False, False]
        channel_tx(self.OPTS)
        mock_chdir.assert_has_calls([
            call('./a_dir'),
            call(PWD)
        ])
        mock_path.exists.assert_called_once_with('a-channel.tx')
        mock_execute.assert_called_once_with(
            'configtxgen -profile AProfile -channelID a-channel -outputCreateChannelTx a-channel.tx', verbose=False)
        mock_print.assert_not_called()
        mock_secret_from_file.assert_called_once_with(
            secret='a-channel-secret', namespace='peer-namespace',
            key='a-channel.tx', filename='a-channel.tx', verbose=False
        )

    @mock.patch('nephos.fabric.crypto.secret_from_file')
    @mock.patch('nephos.fabric.crypto.print')
    @mock.patch('nephos.fabric.crypto.path')
    @mock.patch('nephos.fabric.crypto.execute')
    @mock.patch('nephos.fabric.crypto.chdir')
    def test_again(self, mock_chdir, mock_execute, mock_path, mock_print, mock_secret_from_file):
        mock_path.exists.side_effect = [True, True]
        channel_tx(self.OPTS, True)
        mock_chdir.assert_has_calls([
            call('./a_dir'),
            call(PWD)
        ])
        mock_path.exists.assert_called_once_with('a-channel.tx')
        mock_execute.assert_not_called()
        mock_print.assert_called_once_with('a-channel.tx already exists')
        mock_secret_from_file.assert_called_once_with(
            secret='a-channel-secret', namespace='peer-namespace',
            key='a-channel.tx', filename='a-channel.tx', verbose=True
        )
