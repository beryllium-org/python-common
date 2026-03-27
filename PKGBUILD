#Maintainer: Bill Sideris <bill88t@feline.gr>

pkgname=python-beryllium-common
pkgver=1.11.0
pkgrel=2
depends=('python>=3.12' 'python-pyrunning' 'python-pysetting' 'pyalpm' 'python-qrcode')
url="https://github.com/beryllium-org/python-common"
license=('GPLv3')
arch=('any')
makedepends=('python-setuptools' 'python-pipenv')
pkgdesc="Common python functions used in Beryllium applications"

conflicts=('python-bredos-common')
replaces=('python-bredos-common')

build() {
    cd $srcdir/..
    python setup.py build
}

package() {
    install -Dm644 $srcdir/../LICENSE $pkgdir/usr/share/licenses/$pkgname/LICENSE
    cd $srcdir/..
    python setup.py install --root=$pkgdir --optimize=1 --skip-build
}
